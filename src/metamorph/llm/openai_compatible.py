"""Any OpenAI-compatible chat endpoint: OpenAI, Ollama (http://localhost:11434/v1), Groq, vLLM..."""

from __future__ import annotations

from typing import Any

import httpx

from metamorph.llm.base import LLMError, LLMProvider, LLMRequest, LLMResult, per_mtok

OLLAMA_URL = "http://localhost:11434/v1"


class OpenAICompatibleProvider(LLMProvider):
    def __init__(
        self,
        model: str,
        base_url: str = OLLAMA_URL,
        api_key: str | None = None,
        price_in: float = 0.0,
        price_out: float = 0.0,
        timeout_s: float = 120.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self.price_in, self.price_out = price_in, price_out
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self.client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"), headers=headers, timeout=timeout_s
        )

    async def complete(self, request: LLMRequest) -> LLMResult:
        body: dict[str, Any] = {
            "model": self.model,
            "max_tokens": request.max_tokens,
            "messages": [
                {"role": "system", "content": request.system},
                {"role": "user", "content": request.prompt},
            ],
        }
        if request.schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": "result", "schema": request.schema, "strict": True},
            }
        try:
            response = await self.client.post("/chat/completions", json=body)
        except httpx.HTTPError as exc:
            raise LLMError(f"cannot reach {self.client.base_url}: {exc}") from exc
        if response.is_error:
            raise LLMError(f"HTTP {response.status_code}: {response.text[:200]}")
        data = response.json()
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError(f"unexpected response shape: {str(data)[:200]}") from exc
        usage = data.get("usage") or {}
        tokens_in = int(usage.get("prompt_tokens", 0))
        tokens_out = int(usage.get("completion_tokens", 0))
        return LLMResult(
            text=text,
            model=str(data.get("model", self.model)),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=per_mtok(tokens_in, tokens_out, self.price_in, self.price_out),
        )

    async def aclose(self) -> None:
        await self.client.aclose()
