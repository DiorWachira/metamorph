"""Freeze the cabinet's API for the read-only public demo. Run from a project with stored runs:

    cd examples/cv_skills && python ../../ui/scripts/make_snapshot.py

Writes ui/demo/snapshot/api/**.json, one file per GET the UI makes. The demo build serves these in
place of the API (see `request` in ui/src/api.ts), and the Pages workflow publishes the result.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from metamorph.config import load_config
from metamorph.server.app import create_app

OUT = Path(__file__).resolve().parents[1] / "demo" / "snapshot"


def main() -> None:
    client = TestClient(create_app(load_config(Path("metamorph.yaml"))))

    def save(path: str) -> dict | list:
        response = client.get(path)
        response.raise_for_status()
        target = OUT / f"{path.lstrip('/')}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(response.json(), ensure_ascii=False), encoding="utf-8", newline="\n"
        )
        return response.json()

    shutil.rmtree(OUT, ignore_errors=True)
    for path in ("/api/overview", "/api/relations", "/api/proposals"):
        save(path)
    runs = save("/api/runs")
    cases = 0
    for run in [*runs, {"id": "latest"}]:
        report = save(f"/api/runs/{run['id']}")
        for case in report["cases"]:
            save(f"/api/cases/{case['id']}")
            cases += 1
    size = sum(f.stat().st_size for f in OUT.rglob("*.json")) // 1024
    print(f"{len(runs)} runs, {cases} cases, {size} KB in {OUT}")


if __name__ == "__main__":
    main()
