"""Call an HTTP endpoint. The input dict is the JSON body (POST/PUT) or query string (GET)."""

from __future__ import annotations

import json

import httpx

from metamorph.adapters.base import OutputExtractor, Target, TargetResponse
from metamorph.config import HttpTargetConfig
from metamorph.errors import RetryableTargetError, TargetError
from metamorph.types import Input
from metamorph.util import canonical_json, sha256

_RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("retry-after")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None  # HTTP-date form; fall back to our own backoff


class HttpTarget(Target):
    def __init__(self, config: HttpTargetConfig, client: httpx.AsyncClient | None = None) -> None:
        self.config = config
        self.extract = OutputExtractor(config.output_path)
        self.client = client or httpx.AsyncClient(timeout=config.timeout_s)

    @property
    def fingerprint(self) -> str:
        # Header values are left out: they hold credentials, and rotating a key should not
        # invalidate the cache.
        identity = self.config.model_dump(exclude={"headers", "timeout_s"})
        identity["header_names"] = sorted(self.config.headers)
        return sha256(canonical_json(identity))

    async def call(self, payload: Input) -> TargetResponse:
        cfg = self.config
        try:
            if cfg.method == "GET":
                params = {k: v if isinstance(v, str) else json.dumps(v) for k, v in payload.items()}
                response = await self.client.get(cfg.url, params=params, headers=cfg.headers)
            else:
                response = await self.client.request(
                    cfg.method, cfg.url, json=payload, headers=cfg.headers
                )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise RetryableTargetError(f"{type(exc).__name__}: {exc}") from exc

        if response.status_code in _RETRYABLE_STATUS:
            raise RetryableTargetError(
                f"HTTP {response.status_code}", retry_after=_retry_after(response)
            )
        if response.is_error:
            raise TargetError(f"HTTP {response.status_code}: {response.text[:200]}")

        if cfg.output_path is None:
            return TargetResponse(text=response.text)
        try:
            body = response.json()
        except ValueError as exc:
            raise TargetError("output_path is set but the response is not JSON") from exc
        return TargetResponse(text=self.extract(body))

    async def aclose(self) -> None:
        await self.client.aclose()
