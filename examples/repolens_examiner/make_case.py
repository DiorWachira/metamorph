"""Write seeds.jsonl and recordings.jsonl for the RepoLens Examiner case study.
# ruff: noqa: E501  (the follow-ups are data, kept whole on one line)

Seeds: the Examiner's own suggested prompts and follow-ups plus plain questions, each asked of three
real examinations (reports/), from the case-file page, with a line of the chart open where the
question is about "this" line.

Follow-ups: written by hand in one pass, before any run, because no API key was available. They are
what a person might plausibly type, and are stored in replay format. To use a real helper model
instead, set `llm: {provider: anthropic, record_to: recordings.jsonl}` in metamorph.yaml.
"""

import json
from pathlib import Path

from metamorph.llm.base import LLMResult
from metamorph.llm.replay import recording_line
from metamorph.transforms import build_transform
from metamorph.transforms.llm import LLMRewrite, rewrite_request

HERE = Path(__file__).parent
TRANSFORMS: dict[str, LLMRewrite] = {
    "paraphrase": build_transform("paraphrase", {}),  # type: ignore[dict-item]
    "code_switch": build_transform("code_switch", {"style": "sheng"}),  # type: ignore[dict-item]
    "formality": build_transform("formality", {"direction": "polite"}),  # type: ignore[dict-item]
}

# (slug, question, needs a line open, paraphrase, code switch, polite)
QUESTIONS = [
    (
        "review",
        "Give me an initial review of this report and a prioritized fix plan.",
        False,
        "Please look over this report and tell me what to repair, most important items first.",
        "Manze, nipe review ya hii report na fix plan, vitu muhimu kwanza.",
        "Could you please provide an initial review of this report along with a prioritized fix plan? Thank you.",
    ),
    (
        "first",
        "What should I fix first, and why?",
        False,
        "Which problem should I deal with before the others, and what's the reason?",
        "Nifix nini kwanza, na kwa nini?",
        "Would you kindly tell me what I should fix first, and why?",
    ),
    (
        "explain",
        "Explain the check I'm looking at and how to resolve it.",
        True,
        "What does the check I have open mean, and how can I clear it?",
        "Hii check niko nayo inamaanisha nini, na nairesolve aje?",
        "Could you please explain the check I am looking at and how to resolve it?",
    ),
    (
        "false-positives",
        "Which of these findings could be false positives?",
        False,
        "Could any of these results be wrong, or not real problems at all?",
        "Ni findings gani hapa zinaweza kuwa false positives?",
        "Would you be so kind as to tell me which of these findings could be false positives?",
    ),
    (
        "how-fix",
        "How do I fix this check?",
        True,
        "What do I need to do to clear this one?",
        "Hii check naifix aje?",
        "Could you please tell me how I might fix this check?",
    ),
    (
        "whole-plan",
        "Build a fix plan for the whole report",
        False,
        "Put together a list of repairs covering everything in the report.",
        "Nipangie fix plan ya report yote.",
        "Would you please build a fix plan for the whole report?",
    ),
    (
        "important",
        "What is the most important thing to do next?",
        False,
        "What matters most for me to work on now?",
        "Kitu muhimu zaidi ya kufanya next ni gani?",
        "May I ask what the most important thing to do next would be?",
    ),
    (
        "meaning",
        "What does this line mean?",
        True,
        "Can you tell me what this result is saying?",
        "Hii line inamaanisha nini?",
        "Could you kindly tell me what this line means?",
    ),
    (
        "healthy",
        "Is this repository healthy overall?",
        False,
        "Overall, is this repo in good shape?",
        "Hii repo iko poa kwa ujumla?",
        "May I ask whether this repository is healthy overall?",
    ),
    (
        "score",
        "What steps should I take to improve the score?",
        False,
        "How can I raise the score? Walk me through what to do.",
        "Ni steps gani nifuate niongeze score?",
        "Could you please advise what steps I should take to improve the score?",
    ),
]

REPORTS = ("flex", "repolens", "metamorph")


def main() -> None:
    seeds = []
    for report in REPORTS:
        checks = json.loads((HERE / "reports" / f"{report}.json").read_text(encoding="utf-8"))[
            "checks"
        ]
        open_line = next((c["id"] for c in checks if c["status"] != "pass"), checks[0]["id"])
        for slug, question, needs_line, *_ in QUESTIONS:
            payload = {"question": question, "report": report}
            if needs_line:
                payload["focus"] = open_line
            seeds.append({"id": f"{report}-{slug}", "tags": ["examiner"], "input": payload})
    (HERE / "seeds.jsonl").write_text(
        "".join(json.dumps(s) + "\n" for s in seeds), encoding="utf-8"
    )

    lines = []
    for _, question, _, paraphrase, code_switch, polite in QUESTIONS:
        for name, rewritten in (
            ("paraphrase", paraphrase),
            ("code_switch", code_switch),
            ("formality", polite),
        ):
            request = rewrite_request(TRANSFORMS[name].steps()[0], question)
            result = LLMResult(
                text=json.dumps({"rewritten": rewritten}, ensure_ascii=False), model="authored"
            )
            lines.append(recording_line(request, result, f"transform:{name}"))
    (HERE / "recordings.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(seeds)} seeds, {len(lines)} recordings")


if __name__ == "__main__":
    main()
