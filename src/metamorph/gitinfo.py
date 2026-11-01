"""Git metadata for run snapshots and code-aware cache keys."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from metamorph.util import sha256


@dataclass(frozen=True)
class GitInfo:
    sha: str | None
    code_fingerprint: str  # changes when HEAD or tracked files change


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True, timeout=10, check=True
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout


def git_info(cwd: Path) -> GitInfo:
    head = _git(["rev-parse", "HEAD"], cwd)
    sha = os.environ.get("GITHUB_SHA") or (head.strip() if head else None)
    diff = _git(["diff", "HEAD"], cwd) or ""
    return GitInfo(sha=sha, code_fingerprint=sha256(head or "nogit", diff))
