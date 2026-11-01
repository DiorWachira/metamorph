"""Claude via the official Anthropic SDK (`pip install metamorph[llm]`)."""

from __future__ import annotations

from typing import Any

from metamorph.errors import ConfigError
from metamorph.llm.base import LLMError, LLMProvider, LLMRequest, LLMResult, per_mtok

# USD per million tokens (input, output).
PRICES: dict[str, tuple[float, float]] = {
    "claude-fable-5-1": (10.0, 50.0),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}
# Refusals are routed to Anthropic's recommended fallback model server-side.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider(LLMProvider):
    def __init__(
        self,
        model: str = "claude-opus-5-5",
        effort: str = "low",
        api_key: str | None = None,
        client: Any = None,
    ) -> None:
        self.model = model
        self.effort = effort
        if client is None:
            try:
                from anthropic import AsyncAnthropic
            except ImportError as exc:
                raise ConfigError(
                    "llm.provider anthropic needs the SDK: pip install 'metamorph[llm]'"
                ) from exc
            # Credentials resolve from ANTHROPIC_API_KEY or an `ant auth login` profile.
            client = AsyncAnthropic(api_key=api_key) if api_key else AsyncAnthropic()
        self.client = client

    async def complete(self, request: LLMRequest) -> LLMResult:
        import anthropic

        output_config: dict[str, Any] = {"effort": self.effort}
        if request.schema is not None:
            output_config["format"] = {"type": "json_schema", "schema": request.schema}
        try:
            response = await self.client.beta.messages.create(
                model=self.model,
                max_tokens=request.max_tokens,
                system=request.system,
                messages=[{"role": "user", "content": request.prompt}],
                output_config=output_config,
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError(f"cannot reach the Anthropic API: {exc}") from exc

        if response.stop_reason == "refusal":
            raise LLMError("the helper model declined this request")
        text = "".join(block.text for block in response.content if block.type == "text")
        usage = response.usage
        price_in, price_out = PRICES.get(response.model, PRICES.get(self.model, (0.0, 0.0)))
        return LLMResult(
            text=text,
            model=response.model,
            tokens_in=usage.input_tokens,
            tokens_out=usage.output_tokens,
            cost_usd=per_mtok(usage.input_tokens, usage.output_tokens, price_in, price_out),
        )

    async def aclose(self) -> None:
        await self.client.close()
