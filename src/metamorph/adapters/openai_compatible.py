"""A prompt-only app under test: system prompt file + templated user message on a chat endpoint."""

from __future__ import annotations

import os
import string
from pathlib import Path

import httpx

from metamorph.adapters.base import Target, TargetResponse
from metamorph.config import OpenAICompatibleTargetConfig
from metamorph.errors import ConfigError, RetryableTargetError, TargetError
from metamorph.llm.base import per_mtok
from metamorph.types import Input
from metamorph.util import canonical_json, sha256

_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


class OpenAICompatibleTarget(Target):
    def __init__(
        self,
        config: OpenAICompatibleTargetConfig,
        base_dir: Path,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.config = config
        prompt_path = config.system_prompt_file
        prompt_path = prompt_path if prompt_path.is_absolute() else base_dir / prompt_path
        if not prompt_path.exists():
            raise ConfigError(f"system_prompt_file not found: {prompt_path}")
        self.system_prompt = prompt_path.read_text(encoding="utf-8")
        self.fields = [f for _, f, _, _ in string.Formatter().parse(config.user_template) if f]

        headers: dict[str, str] = {}
        if config.api_key_env:
            key = os.environ.get(config.api_key_env)
            if not key:
                raise ConfigError(f"target.api_key_env: {config.api_key_env} is not set")
            headers["Authorization"] = f"Bearer {key}"
        self.client = client or httpx.AsyncClient(
            base_url=config.base_url.rstrip("/"), headers=headers, timeout=config.timeout_s
        )

    @property
    def fingerprint(self) -> str:
        # The system prompt is part of the app's behaviour: editing it invalidates the cache.
        identity = self.config.model_dump(mode="json", exclude={"api_key_env", "timeout_s"})
        return sha256(canonical_json(identity), self.system_prompt)

    def _user_message(self, payload: Input) -> str:
        missing = [f for f in self.fields if f not in payload]
        if missing:
            raise TargetError(f"user_template needs input fields {missing}")
        return self.config.user_template.format(**payload)

    async def call(self, payload: Input) -> TargetResponse:
        cfg = self.config
        body = {
            "model": cfg.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": self._user_message(payload)},
            ],
        }
        try:
            response = await self.client.post("/chat/completions", json=body)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise RetryableTargetError(f"{type(exc).__name__}: {exc}") from exc
        if response.status_code in _RETRYABLE_STATUS:
            raise RetryableTargetError(f"HTTP {response.status_code}")
        if response.is_error:
            raise TargetError(f"HTTP {response.status_code}: {response.text[:200]}")
        data = response.json()
        try:
            text = data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise TargetError(f"unexpected response shape: {str(data)[:200]}") from exc
        usage = data.get("usage") or {}
        tokens_in, tokens_out = (
            int(usage.get("prompt_tokens", 0)),
            int(usage.get("completion_tokens", 0)),
        )
        return TargetResponse(
            text=text,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            cost_usd=per_mtok(
                tokens_in, tokens_out, cfg.input_cost_per_mtok, cfg.output_cost_per_mtok
            ),
        )

    async def aclose(self) -> None:
        await self.client.aclose()
