"""The triage API, exercised against a real stored run."""

from __future__ import annotations

from pathlib import Path

import pytest
from fakes import ScriptedTarget
from fastapi.testclient import TestClient
from support import SEEDS, make_config

from metamorph.server.app import STATIC, create_app
from metamorph.suite import run_suite


@pytest.fixture
async def client(tmp_path: Path) -> TestClient:
    originals = {s["input"]["question"] for s in SEEDS}
    cfg = make_config(tmp_path, relations=["typo-robustness", "distractor-invariance"])
    await run_suite(
        cfg, target=ScriptedTarget(lambda p, n: "A" if p["question"] in originals else "B")
    )
    return TestClient(create_app(cfg))


def test_overview_runs_and_report(client: TestClient) -> None:
    overview = client.get("/api/overview").json()
    assert overview["runs"] == 1 and overview["target"] == "python"
    runs = client.get("/api/runs").json()
    assert runs[0]["violations"] == 10
    report = client.get("/api/runs/latest").json()
    assert report["run"]["id"] == runs[0]["id"]
    assert {"unstable_inputs", "baseline_effect"} <= report.keys()
    assert client.get("/api/runs/nope").status_code == 404


def test_case_detail_has_diffs_and_neighbours(client: TestClient) -> None:
    report = client.get("/api/runs/latest").json()
    first, second = [c["id"] for c in report["cases"] if c["status"] == "violation"][:2]
    detail = client.get(f"/api/cases/{first}").json()
    assert detail["output_diff"] == {"left": [["delete", "A"]], "right": [["insert", "B"]]}
    assert detail["changed_field"] == "question"
    assert detail["neighbours"] == {"previous": None, "next": second}
    assert client.get("/api/cases/999999").status_code == 404


def test_triage_round_trip(client: TestClient) -> None:
    report = client.get("/api/runs/latest").json()
    violation = next(c for c in report["cases"] if c["status"] == "violation")
    response = client.post(
        f"/api/cases/{violation['id']}/triage", json={"verdict": "true_bug", "note": "real"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["case"]["triage"] == "true_bug" and body["case"]["note"] == "real"
    assert body["stats"]["reviewed"] == 1 and body["stats"]["precision"] == 1.0

    bad = client.post(f"/api/cases/{violation['id']}/triage", json={"verdict": "maybe"})
    assert bad.status_code == 422


def test_relations_catalogue(client: TestClient) -> None:
    data = client.get("/api/relations").json()
    by_id = {r["id"]: r for r in data["relations"]}
    assert len(by_id) == 12
    assert by_id["typo-robustness"]["enabled"] and not by_id["negation-flip"]["enabled"]
    assert by_id["code-switch-invariance"]["llm"] and not by_id["typo-robustness"]["llm"]
    assert data["min_reviewed"] == 20 and data["min_precision"] == 0.8


def test_lab_previews_deterministic_transforms(client: TestClient) -> None:
    response = client.post(
        "/api/lab/transform",
        json={
            "transform": "typos",
            "params": {"rate": 1.0},
            "text": "Which county borders Nairobi?",
        },
    )
    body = response.json()
    assert body["changed"] and body["text"] != "Which county borders Nairobi?"
    unchanged = client.post("/api/lab/transform", json={"transform": "typos", "text": "is it"})
    assert unchanged.json()["changed"] is False
    llm = client.post("/api/lab/transform", json={"transform": "paraphrase", "text": "hello"})
    assert llm.status_code == 400
    missing = client.post(
        "/api/lab/transform", json={"transform": "shuffle_documents", "text": "q"}
    )
    assert missing.json()["changed"] is False


@pytest.mark.skipif(not (STATIC / "index.html").exists(), reason="UI not built")
def test_spa_fallback(client: TestClient) -> None:
    page = client.get("/runs/anything")
    assert page.status_code == 200 and '<div id="root">' in page.text
    assert client.get("/api/unknown").status_code == 404


def test_triage_writes_learned_file(client: TestClient, tmp_path: Path) -> None:
    report = client.get("/api/runs/latest").json()
    violation = next(c for c in report["cases"] if c["status"] == "violation")
    client.post(f"/api/cases/{violation['id']}/triage", json={"verdict": "false_alarm"})
    learned = (tmp_path / "relations" / "learned.yaml").read_text(encoding="utf-8")
    assert "false_alarms: 1" in learned


async def test_proposals_api(tmp_path: Path) -> None:
    import json

    from fakes import ScriptedLLM

    from metamorph.collection import proposals_path, save_proposals
    from metamorph.llm.service import LLMService
    from metamorph.miner import mine
    from metamorph.relations import builtin_specs

    cfg = make_config(tmp_path / "p")
    proposal = {
        "id": "names-do-not-matter",
        "requirement": "Names must not matter.",
        "description": "Swapping names keeps the answer.",
        "transform": "swap_entities",
        "transform_params_json": "{}",
        "comparator": "token_f1",
        "comparator_params_json": "{}",
        "threshold": None,
        "expected": "invariant",
        "rationale": "Bias.",
    }
    llm = LLMService(ScriptedLLM(lambda r: json.dumps({"proposals": [proposal]})))
    result = await mine(llm, "Names must not matter.", "SPEC.md", set(builtin_specs()))
    save_proposals(proposals_path(cfg), result.proposals)

    api = TestClient(create_app(cfg))
    assert [p["spec"]["id"] for p in api.get("/api/proposals").json()] == ["names-do-not-matter"]
    assert api.post("/api/proposals/names-do-not-matter/approve").json() == []
    relations = {r["id"]: r for r in api.get("/api/relations").json()["relations"]}
    assert relations["names-do-not-matter"]["enabled"]
    assert relations["names-do-not-matter"]["requirement"] == "Names must not matter."
    assert api.post("/api/proposals/names-do-not-matter/reject").status_code == 400
