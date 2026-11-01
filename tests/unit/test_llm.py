"""Helper-LLM providers, the service (cache, budget, recording) and replay."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from fakes import ScriptedLLM

from metamorph.errors import ConfigError
from metamorph.llm.base import LLMError, LLMRequest
from metamorph.llm.claude import FALLBACK_BETA, AnthropicProvider
from metamorph.llm.openai_compatible import OpenAICompatibleProvider
from metamorph.llm.replay import ReplayProvider
from metamorph.llm.service import LLMService
from metamorph.runner.budget import Budget, BudgetExhausted
from metamorph.runner.cache import Cache

REQUEST = LLMRequest(system="sys", prompt="Rewrite: hello", schema={"type": "object"})


class FakeMessages:
    def __init__(self, response: Any) -> None:
        self.response = response
        self.kwargs: dict[str, Any] = {}

    async def create(self, **kwargs: Any) -> Any:
        self.kwargs = kwargs
        return self.response


def claude_response(text: str, stop_reason: str = "end_turn") -> Any:
    return SimpleNamespace(
        stop_reason=stop_reason,
        model="claude-opus-5-5",
        content=[SimpleNamespace(type="thinking"), SimpleNamespace(type="text", text=text)],
        usage=SimpleNamespace(input_tokens=1_000_000, output_tokens=100_000),
    )


async def test_anthropic_provider_request_shape_and_cost() -> None:
    messages = FakeMessages(claude_response('{"rewritten": "hi"}'))
    client = SimpleNamespace(beta=SimpleNamespace(messages=messages))
    provider = AnthropicProvider("claude-opus-5-5", effort="low", client=client)
    result = await provider.complete(REQUEST)

    sent = messages.kwargs
    assert sent["model"] == "claude-opus-5-5"
    assert sent["output_config"] == {
        "effort": "low",
        "format": {"type": "json_schema", "schema": {"type": "object"}},
    }
    assert sent["betas"] == [FALLBACK_BETA] and sent["fallbacks"] == "default"
    assert "temperature" not in sent and "thinking" not in sent
    assert result.text == '{"rewritten": "hi"}'
    assert result.cost_usd == pytest.approx(4.0 + 2.0)  # 1M in at $4, 100k out at $20/M


async def test_anthropic_refusal_is_an_llm_error() -> None:
    client = SimpleNamespace(
        beta=SimpleNamespace(messages=FakeMessages(claude_response("", "refusal")))
    )
    with pytest.raises(LLMError, match="declined"):
        await AnthropicProvider(client=client).complete(REQUEST)


async def test_openai_compatible_provider() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(
            200,
            json={
                "model": "llama3.2",
                "choices": [{"message": {"content": '{"rewritten": "x"}'}}],
                "usage": {"prompt_tokens": 2_000_000, "completion_tokens": 0},
            },
        )

    client = httpx.AsyncClient(base_url="http://llm", transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleProvider("llama3.2", price_in=0.5, client=client)
    result = await provider.complete(REQUEST)
    assert seen["messages"][0] == {"role": "system", "content": "sys"}
    assert seen["response_format"]["type"] == "json_schema"
    assert result.text == '{"rewritten": "x"}' and result.cost_usd == pytest.approx(1.0)


async def test_openai_compatible_http_error() -> None:
    client = httpx.AsyncClient(
        base_url="http://llm",
        transport=httpx.MockTransport(lambda r: httpx.Response(500, text="boom")),
    )
    with pytest.raises(LLMError, match="HTTP 500"):
        await OpenAICompatibleProvider("m", client=client).complete(REQUEST)


async def test_service_caches_charges_budget_and_records(tmp_path: Path) -> None:
    provider = ScriptedLLM(lambda r: '{"rewritten": "hi"}', cost=0.4)
    cache = Cache(tmp_path / "c.sqlite")
    budget = Budget(limit_usd=0.5)
    record = tmp_path / "rec.jsonl"
    service = LLMService(provider, cache, budget, record_to=record)

    first = await service.complete("p", REQUEST)
    again = await service.complete("p", REQUEST)  # cache hit: no call, no charge
    assert first.text == again.text and len(provider.requests) == 1
    assert service.stats.cache_hits == 1 and budget.spent_usd == pytest.approx(0.4)

    await service.complete("other-purpose", REQUEST)  # 0.8 spent: over the limit now
    with pytest.raises(BudgetExhausted):
        await service.complete("third", REQUEST)
    assert len(record.read_text(encoding="utf-8").splitlines()) == 2
    cache.close()


async def test_service_rejects_invalid_json() -> None:
    service = LLMService(ScriptedLLM(lambda r: "not json"))
    with pytest.raises(LLMError, match="invalid JSON"):
        await service.complete_json("p", REQUEST)


async def test_record_then_replay(tmp_path: Path) -> None:
    record = tmp_path / "rec.jsonl"
    live = LLMService(ScriptedLLM(lambda r: '{"rewritten": "live"}'), record_to=record)
    await live.complete("p", REQUEST)

    replay = ReplayProvider(record)
    assert (await replay.complete(REQUEST)).text == '{"rewritten": "live"}'
    with pytest.raises(LLMError, match="no recording"):
        await replay.complete(LLMRequest(system="sys", prompt="something else"))


def test_replay_file_errors(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        ReplayProvider(tmp_path / "missing.jsonl")
    bad = tmp_path / "bad.jsonl"
    bad.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid recording"):
        ReplayProvider(bad)
