"""Metamorph target: RepoLens's offline Examiner, run from a local clone of RepoLens.

The Examiner's offline mode is browser JavaScript, so each call runs it in Node. Set REPOLENS_DIR
if the clone is not next to this repository. The case study pins the commit (see metamorph.yaml).
"""

import json
import os
import subprocess
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
REPOLENS = Path(os.environ.get("REPOLENS_DIR", HERE.parents[2] / "repolens"))


def answer(payload: dict[str, Any]) -> str:
    report = json.loads(
        (HERE / "reports" / f"{payload['report']}.json").read_text(encoding="utf-8")
    )
    request = {
        "dir": str(REPOLENS),
        "question": payload["question"],
        "report": report,
        "focus": payload.get("focus"),
    }
    done = subprocess.run(
        ["node", str(HERE / "run_offline.cjs")],
        input=json.dumps(request),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=True,
    )
    result = json.loads(done.stdout)
    steps = [f"{step['title']}: {step['detail']}" for step in result["workflow"]]
    return "\n".join([result["answer"], *steps])
