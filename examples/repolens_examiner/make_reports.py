"""Write reports/*.json: real RepoLens examinations, in the shape its web server sends the page.

REPOLENS_DIR=../../../repolens python make_reports.py NAME=OWNER/REPO=PATH ...
"""

import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
REPOLENS = Path(os.environ.get("REPOLENS_DIR", HERE.parents[2] / "repolens"))

for spec in sys.argv[1:]:
    name, slug, path = spec.split("=", 2)
    out = subprocess.run(
        [sys.executable, "-m", "repolens", path, "--json"],
        cwd=REPOLENS,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout
    report = json.loads(out)
    checks = []
    for check in report["checks"]:
        shaped = {key: check[key] for key in ("id", "title", "status", "detail")}
        if check.get("evidence"):
            shaped["locations"] = check["evidence"]
        checks.append(shaped)
    shaped_report = {"root": f"github.com/{slug}", "score": report["score"], "checks": checks}
    (HERE / "reports" / f"{name}.json").write_text(
        json.dumps(shaped_report, indent=2) + "\n", encoding="utf-8"
    )
    print(name, report["score"], [(c["id"], c["status"]) for c in checks if c["status"] != "pass"])
