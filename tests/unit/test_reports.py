"""Word diffs, the HTML report and the openai_compatible target adapter."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from fakes import ScriptedTarget
from support import make_config

from metamorph.adapters.openai_compatible import OpenAICompatibleTarget
from metamorph.config import OpenAICompatibleTargetConfig
from metamorph.diff import word_diff
from metamorph.errors import ConfigError, RetryableTargetError, TargetError
from metamorph.reports import render_html, render_junit
from metamorph.suite import run_suite


def test_word_diff_marks_changes_on_each_side() -> None:
    left, right = word_diff("M-Pesa launched in 2007", "M-Pesa launched in March 2007")
    assert "".join(t for _, t in left) == "M-Pesa launched in 2007"
    assert "".join(t for _, t in right) == "M-Pesa launched in March 2007"
    assert ("insert", "March ") in right and all(op != "insert" for op, _ in left)
    left, right = word_diff("yes", "no")
    assert left == [("delete", "yes")] and right == [("insert", "no")]


async def test_html_report_renders_and_escapes(tmp_path: Path) -> None:
    originals = {"<b>Which county</b> is it?"}
    seeds = [{"id": "x", "input": {"question": "<b>Which county</b> is it?"}}]
    cfg = make_config(tmp_path, seeds=seeds)
    report = await run_suite(
        cfg,
        target=ScriptedTarget(
            lambda p, n: (
                "<script>alert(1)</script>" if p["question"] not in originals else "Nairobi"
            )
        ),
    )
    html = render_html(report)
    assert "Gate failed" in html and "MM&middot;" in html
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
    assert "--carmine" in html  # the design system is inlined
    assert render_junit(report).count("<failure") == 1


def target_config(tmp_path: Path, **extra: Any) -> OpenAICompatibleTargetConfig:
    prompt = tmp_path / "system.txt"
    prompt.write_text("Extract skills as JSON.", encoding="utf-8")
    return OpenAICompatibleTargetConfig.model_validate(
        {
            "type": "openai_compatible",
            "model": "llama3.2",
            "system_prompt_file": str(prompt),
            "user_template": "CV: {cv_text}",
            "input_cost_per_mtok": 1.0,
            **extra,
        }
    )


async def test_openai_compatible_target(tmp_path: Path) -> None:
    sent: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        sent.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"skills": ["Python"]}'}}],
                "usage": {"prompt_tokens": 1_000_000, "completion_tokens": 10},
            },
        )

    client = httpx.AsyncClient(base_url="http://x", transport=httpx.MockTransport(handler))
    config = target_config(tmp_path)
    target = OpenAICompatibleTarget(config, tmp_path, client=client)
    response = await target.call({"cv_text": "I know Python"})
    assert sent["messages"][0]["content"] == "Extract skills as JSON."
    assert sent["messages"][1]["content"] == "CV: I know Python"
    assert response.text == '{"skills": ["Python"]}' and response.cost_usd == pytest.approx(1.0)
    with pytest.raises(TargetError, match="needs input fields"):
        await target.call({"other": 1})

    fp = target.fingerprint
    (tmp_path / "system.txt").write_text("A different prompt.", encoding="utf-8")
    assert OpenAICompatibleTarget(config, tmp_path, client=client).fingerprint != fp


async def test_openai_compatible_target_errors(tmp_path: Path) -> None:
    client = httpx.AsyncClient(
        base_url="http://x", transport=httpx.MockTransport(lambda r: httpx.Response(429))
    )
    target = OpenAICompatibleTarget(target_config(tmp_path), tmp_path, client=client)
    with pytest.raises(RetryableTargetError):
        await target.call({"cv_text": "x"})
    with pytest.raises(ConfigError, match="system_prompt_file"):
        OpenAICompatibleTarget(
            target_config(tmp_path).model_copy(update={"system_prompt_file": Path("nope.txt")}),
            tmp_path,
        )


async def test_markdown_summary_for_pull_requests(tmp_path: Path) -> None:
    from metamorph.reports.markdown import MARKER, render_markdown

    originals = {"Which county | pipe?"}
    seeds = [{"id": "x", "input": {"question": "Which county | pipe?"}}]
    cfg = make_config(tmp_path, seeds=seeds)
    report = await run_suite(
        cfg,
        target=ScriptedTarget(lambda p, n: "A | B" if p["question"] in originals else "C"),
    )
    md = render_markdown(report)
    assert md.startswith(MARKER)
    assert "🔴 **Gate failed**" in md
    assert "| `typo-robustness` | **blocking** | 1 | 1 | 0 |" in md
    assert "A \| B" in md  # pipes in answers cannot break the table


def test_action_definition() -> None:
    import yaml

    root = Path(__file__).parents[2]
    action = yaml.safe_load((root / "action.yml").read_text(encoding="utf-8"))
    assert action["runs"]["using"] == "composite"
    steps = {s.get("name", s.get("uses")): s for s in action["runs"]["steps"]}
    assert steps["Comment on the pull request"]["continue-on-error"] is True
    assert "fail-on-gate" in action["inputs"] and "exit-code" in action["outputs"]
    names = list(steps)
    assert names.index("Apply the gate") == len(names) - 1  # gate last: reports always posted
