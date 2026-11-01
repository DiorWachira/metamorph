"""A stand-in for an LLM skill extractor (like JobBridge's), with sampling noise and a planted bug.

It returns {"skills": [...]} for a CV. Two properties make it a realistic test subject:

* Noise: like an LLM sampled at temperature > 0, repeated calls on the same CV differ a little
  (an occasional skill is dropped, or a related one is added). Naive metamorphic testing blames
  the app for this; Metamorph's self-variance baseline should not.
* Planted bug: it only reads skills from sentences with English cue phrases ("proficient in",
  "experienced in"...), the way a prompt with English-only few-shot examples behaves. CVs written
  in Kenyan English / Kiswahili / Sheng code-switching lose skills. code-switch-invariance should
  catch it. Set CV_FIXED=1 for the corrected extractor.

A real LLM version of this app is prompts/system.txt + metamorph.ollama.yaml.
"""

from __future__ import annotations

import hashlib
import os
import random
import re
import threading
from collections import Counter

SKILLS = [
    "Python", "SQL", "Power BI", "Excel", "Django", "PostgreSQL", "REST APIs", "M-Pesa",
    "Daraja API", "React", "TypeScript", "Figma", "Tailwind CSS", "AWS", "Terraform", "Linux",
    "Kubernetes", "Jira", "Stakeholder management", "Budgeting", "Scrum", "Kotlin", "Flutter",
    "Firebase", "Google Maps API", "PyTorch", "scikit-learn", "NLP", "QuickBooks",
    "Tax compliance", "Auditing",
]  # fmt: skip
RELATED = {
    "Python": "Pandas",
    "React": "JavaScript",
    "AWS": "Cloud computing",
    "Excel": "Data analysis",
    "Django": "Python",
    "Scrum": "Agile",
    "PyTorch": "Deep learning",
}
CUES = re.compile(
    r"\b(proficient in|experienced in|skilled in|worked with|certified in|built|using|"
    r"experience in|expertise in)\b",
    re.I,
)
NOISE = 0.12

_calls: Counter[str] = Counter()
_lock = threading.Lock()


def _mentions(text: str) -> list[str]:
    found = []
    for skill in SKILLS:
        stem = re.escape(skill.rstrip("s")) if skill.endswith("APIs") else re.escape(skill)
        if re.search(rf"(?<![\w-]){stem}", text, re.I):
            found.append(skill)
    return found


def extract_skills(cv: str, fixed: bool = False) -> list[str]:
    """The deterministic core: what the extractor 'means' to answer, before sampling noise."""
    sentences = re.split(r"(?<=[.!?])\s+", cv)
    readable = sentences if fixed else [s for s in sentences if CUES.search(s)]  # the bug
    return _mentions(" ".join(readable))


def extract(payload: dict) -> dict:
    cv = payload["cv_text"]
    with _lock:
        n = _calls[cv]
        _calls[cv] += 1
    skills = extract_skills(cv, fixed=os.environ.get("CV_FIXED") == "1")
    rng = random.Random(hashlib.sha256(f"{cv}|{n}".encode()).hexdigest())
    sampled = [s for s in skills if rng.random() > NOISE]
    sampled += [RELATED[s] for s in skills if s in RELATED and rng.random() < NOISE]
    return {"skills": sorted(set(sampled))}
