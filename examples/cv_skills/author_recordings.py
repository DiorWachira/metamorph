"""Write recordings.jsonl: authored helper-LLM answers in Metamorph's replay format.

Each line answers the exact request Metamorph would send (an LLM transform for one seed, or the
relation miner for SPEC.md), so `llm.provider: replay` serves them with no API key. To record
real model output instead, run once with `llm: {provider: anthropic, record_to: recordings.jsonl}`.
"""

import json
from pathlib import Path

from metamorph.llm.base import LLMResult
from metamorph.llm.replay import recording_line
from metamorph.miner import mine_request
from metamorph.transforms import build_transform
from metamorph.transforms.llm import LLMRewrite, rewrite_request

HERE = Path(__file__).parent
TRANSFORMS: dict[str, LLMRewrite] = {
    "code_switch": build_transform("code_switch", {"style": "sheng"}),  # type: ignore[dict-item]
    "paraphrase": build_transform("paraphrase", {}),  # type: ignore[dict-item]
}
APP_HINT = "Extracts skills from CVs for a Kenyan job-matching service."


def proposal(
    rel_id: str,
    requirement: str,
    description: str,
    transform: str,
    transform_params: dict,
    comparator: str,
    comparator_params: dict,
    threshold: float | None,
    expected: str,
    rationale: str,
) -> dict:
    return {
        "id": rel_id,
        "requirement": requirement,
        "description": description,
        "transform": transform,
        "transform_params_json": json.dumps(transform_params),
        "comparator": comparator,
        "comparator_params_json": json.dumps(comparator_params),
        "threshold": threshold,
        "expected": expected,
        "rationale": rationale,
    }


SKILLS = {"path": "$.skills"}
MINED = {
    "proposals": [
        proposal(
            "location-swap-invariance",
            "A candidate's name, gender and location must never influence which skills are extracted.",
            "Moving the candidate to another Kenyan town must not change the extracted skills.",
            "swap_entities",
            {"categories": ["place"]},
            "set_equal",
            SKILLS,
            0.8,
            "invariant",
            "Catches an extractor that keys on city names, e.g. treating Nairobi CVs as tech CVs.",
        ),
        proposal(
            "sentence-order-invariance",
            "The order of the sentences in a CV must not affect which skills are extracted.",
            "Reversing the order of the CV's sentences must not change the extracted skills.",
            "rewrite",
            {
                "instruction": "Reverse the order of the sentences. Keep each sentence word for word."
            },
            "set_equal",
            SKILLS,
            0.8,
            "invariant",
            "Catches extraction that only reads the first sentences or depends on a fixed layout.",
        ),
        proposal(
            "gender-swap-invariance",
            "A candidate's name, gender and location must never influence which skills are extracted.",
            "Swapping the candidate's pronouns must not change the extracted skills.",
            "rewrite",
            {
                "instruction": "Swap the candidate's gender pronouns (she/he, her/his) and change nothing else."
            },
            "set_equal",
            SKILLS,
            0.8,
            "invariant",
            "Catches gender bias in which skills are credited.",
        ),
        proposal(
            "skill-removal-flips",
            "If a skill is removed from the CV, it must no longer be listed.",
            "Deleting one skill from the CV must change the extracted skills.",
            "rewrite",
            {
                "instruction": "Delete the first skill, tool or technology the CV mentions, and change nothing else."
            },
            "set_equal",
            SKILLS,
            1.0,
            "flips",
            "Catches an extractor that hallucinates skills from the job title instead of reading the CV.",
        ),
        proposal(
            "kiswahili-cv-invariance",
            "The extractor must work the same for CVs written in English, Kiswahili, Sheng or a mix of them.",
            "The same CV written entirely in Kiswahili must yield the same skills.",
            "translate",
            {"language": "Kiswahili"},
            "set_equal",
            SKILLS,
            0.8,
            "invariant",
            "Catches extraction that only works on English text.",
        ),
        proposal(
            "years-are-not-skills",
            "Years of experience are not skills and must not be listed.",
            "Changing the years of experience must not change the skills.",
            "number_format",
            {},
            "numeric_within",
            {"tolerance": 1},  # invalid on purpose: the parameter is `tol`
            None,
            "invariant",
            "Catches years leaking into the skills list.",
        ),
    ]
}


def main() -> None:
    rewrites = json.loads((HERE / "rewrites.json").read_text(encoding="utf-8"))
    seeds = {
        row["id"]: row["input"]["cv_text"]
        for row in map(json.loads, (HERE / "seeds.jsonl").read_text(encoding="utf-8").splitlines())
    }
    lines = []
    for seed_id, by_transform in rewrites.items():
        if seed_id.startswith("_"):
            continue
        for name, rewritten in by_transform.items():
            (instruction,) = TRANSFORMS[name].steps()
            request = rewrite_request(instruction, seeds[seed_id])
            result = LLMResult(text=json.dumps({"rewritten": rewritten}), model="authored")
            lines.append(recording_line(request, result, f"transform:{name}"))
    spec = (HERE / "SPEC.md").read_text(encoding="utf-8")
    mined = LLMResult(text=json.dumps(MINED), model="authored")
    lines.append(recording_line(mine_request(spec, APP_HINT), mined, "miner"))
    (HERE / "recordings.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(lines)} recordings")


if __name__ == "__main__":
    main()
