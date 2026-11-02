"""Metamorph target: RepoLens's Gemini Examiner, its real `generate_insights`, from a local clone.

Needs GEMINI_API_KEY. Set REPOLENS_DIR if the clone is not next to this repository.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).parent
REPOLENS = Path(os.environ.get("REPOLENS_DIR", HERE.parents[2] / "repolens"))
sys.path.insert(0, str(REPOLENS))

from repolens import ai  # noqa: E402

from metamorph.errors import RetryableTargetError  # noqa: E402

# One model for the whole run. RepoLens falls back to others when one is busy, which would make
# differences between answers mean nothing, so here a busy model is an error to retry instead.
MODEL = "gemini-3.5-flash-lite"
ai.DEFAULT_MODEL = MODEL
ai.FALLBACK_MODELS = ()
os.environ.pop("GEMINI_MODEL", None)


def answer(payload: dict[str, Any]) -> str:
    report_file = HERE / "reports" / f"{payload['report']}.json"
    report = json.loads(report_file.read_text(encoding="utf-8"))
    try:
        result = ai.generate_insights(
            report, question=payload["question"], focus=payload.get("focus")
        )
    except RuntimeError as exc:
        if "429" in str(exc):
            raise RetryableTargetError(str(exc), retry_after=30.0) from exc
        raise
    # Check rather than assume: the run's write-up reports which model really answered.
    with (HERE / ".metamorph" / "models.log").open("a", encoding="utf-8") as log:
        print(result["model"], file=log)
    steps = [f"{step['title']}: {step['detail']}" for step in result.get("workflow", [])]
    return "\n".join([result["answer"], *steps])
