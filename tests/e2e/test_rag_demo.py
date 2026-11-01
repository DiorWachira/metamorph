"""End-to-end: the CLI against the RAG demo, in-process and over real HTTP."""

from __future__ import annotations

import json
import shutil
import socket
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from typer.testing import CliRunner

from metamorph.cli import EXIT_ERROR, EXIT_GATE_FAILED, EXIT_PASS, app

EXAMPLE = Path(__file__).parents[2] / "examples" / "rag_kenya"
runner = CliRunner()


@pytest.fixture
def demo(tmp_path: Path) -> Path:
    """A private copy of the demo, so each test gets its own .metamorph storage."""
    target = tmp_path / "rag_kenya"
    shutil.copytree(EXAMPLE, target, ignore=shutil.ignore_patterns(".metamorph", "__pycache__"))
    return target


def run_cli(*args: str) -> tuple[int, str]:
    result = runner.invoke(app, list(args))
    return result.exit_code, result.output


def latest_json(demo: Path) -> dict[str, Any]:
    newest = max((demo / ".metamorph" / "reports").iterdir(), key=lambda p: p.stat().st_mtime_ns)
    return json.loads((newest / "report.json").read_text(encoding="utf-8"))


def test_gate_catches_the_planted_bug(demo: Path) -> None:
    code, output = run_cli("run", "--gate", "-c", str(demo / "metamorph.yaml"))
    assert code == EXIT_GATE_FAILED, output
    assert "Gate FAILED" in output

    report = latest_json(demo)
    doc_order = [c for c in report["cases"] if c["relation_id"] == "doc-order-invariance"]
    violations = [c for c in doc_order if c["status"] == "violation"]
    assert len(violations) >= len(doc_order) // 2
    case = violations[0]
    assert case["mode"] == "blocking"
    assert case["source_outputs"][0]["text"] != case["followup_output"]["text"]

    junit = next((demo / ".metamorph" / "reports").iterdir()) / "junit.xml"
    assert '<failure message="token F1' in junit.read_text(encoding="utf-8")


def test_rerun_is_free_and_identical(demo: Path) -> None:
    config = str(demo / "metamorph.yaml")
    run_cli("run", "-c", config)
    first = latest_json(demo)
    run_cli("run", "-c", config)
    second = latest_json(demo)

    assert second["run"]["stats"]["cache_hits"] == second["run"]["stats"]["requested"]
    assert second["run"]["total_cost_usd"] == 0.0

    def verdicts(r: dict[str, Any]) -> list[tuple[str, str, str, float]]:
        return [(c["relation_id"], c["seed_id"], c["status"], c["score"]) for c in r["cases"]]

    assert verdicts(second) == verdicts(first)


def test_fixed_app_passes_the_gate(demo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_FIXED", "1")
    code, output = run_cli("run", "--gate", "--no-cache", "-c", str(demo / "metamorph.yaml"))
    assert code == EXIT_PASS, output


def test_report_command(demo: Path) -> None:
    config = str(demo / "metamorph.yaml")
    run_cli("run", "-c", config, "--relations", "doc-order-invariance", "--limit", "3")
    code, output = run_cli("report", "latest", "-c", config, "--format", "junit")
    assert code == EXIT_PASS and output.startswith("<?xml")
    out = demo / "r.json"
    code, _ = run_cli("report", "latest", "-c", config, "-o", str(out))
    assert code == EXIT_PASS and len(json.loads(out.read_text())["cases"]) == 3
    code, output = run_cli("report", "no-such-run", "-c", config)
    assert code == EXIT_ERROR and "no run found" in output


def test_config_errors_exit_2(tmp_path: Path) -> None:
    code, output = run_cli("run", "-c", str(tmp_path / "missing.yaml"))
    assert code == EXIT_ERROR and "metamorph init" in output


def test_init_creates_a_runnable_project(tmp_path: Path) -> None:
    code, _ = run_cli("init", str(tmp_path))
    assert code == EXIT_PASS
    assert (tmp_path / ".gitignore").read_text() == ".metamorph/\n"
    sys.modules.pop("app", None)
    try:
        code, output = run_cli("run", "--gate", "-c", str(tmp_path / "metamorph.yaml"))
    finally:
        sys.modules.pop("app", None)
    assert code == EXIT_PASS, output  # the placeholder has no blocking relations
    code, output = run_cli("init", str(tmp_path))
    assert "skip" in output


@pytest.fixture
def http_server(demo: Path) -> Iterator[int]:
    sys.path.insert(0, str(demo))
    from rag_app import api

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(api, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.05)
    yield port
    server.should_exit = True
    thread.join(timeout=5)
    sys.path.remove(str(demo))


def test_http_adapter_against_the_live_server(demo: Path, http_server: int) -> None:
    config = demo / "metamorph.http.yaml"
    text = config.read_text(encoding="utf-8").replace("8765", str(http_server))
    config.write_text(text, encoding="utf-8")
    code, output = run_cli("run", "--gate", "-c", str(config))
    assert code == EXIT_GATE_FAILED, output
    report = latest_json(demo)
    assert report["run"]["stats"]["errors"] == 0
    assert any(
        c["relation_id"] == "doc-order-invariance" and c["status"] == "violation"
        for c in report["cases"]
    )


CV_EXAMPLE = Path(__file__).parents[2] / "examples" / "cv_skills"


@pytest.fixture
def cv_demo(tmp_path: Path) -> Iterator[Path]:
    """A private copy of the CV demo. The app's sampling noise depends on how many times it has
    seen each CV in this process, so each test imports a fresh copy of the module."""
    target = tmp_path / "cv_skills"
    shutil.copytree(CV_EXAMPLE, target, ignore=shutil.ignore_patterns(".metamorph", "__pycache__"))
    sys.modules.pop("cv_app", None)
    yield target
    sys.modules.pop("cv_app", None)


def test_cv_code_switch_bug_is_caught_without_an_api_key(cv_demo: Path) -> None:
    code, output = run_cli("run", "--gate", "-c", str(cv_demo / "metamorph.yaml"))
    assert code == EXIT_GATE_FAILED, output
    assert "helper model replay" in output and "self-variance baseline (k=3)" in output
    report = latest_json(cv_demo)
    code_switch = [c for c in report["cases"] if c["relation_id"] == "code-switch-invariance"]
    assert code_switch and all(c["status"] == "violation" for c in code_switch)
    assert report["run"]["llm"]["failures"] == 0
    assert (next((cv_demo / ".metamorph" / "reports").iterdir()) / "report.html").exists()


def test_cv_fixed_extractor_passes(cv_demo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CV_FIXED", "1")
    code, output = run_cli("run", "--gate", "--no-cache", "-c", str(cv_demo / "metamorph.yaml"))
    assert code == EXIT_PASS, output
