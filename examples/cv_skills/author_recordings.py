"""Write recordings.jsonl: authored follow-ups in Metamorph's replay format.

Each line answers the exact request the LLM transform would send for that seed, so
`llm.provider: replay` serves them with no API key. To record real model output instead, run the
suite once with `llm: {provider: anthropic, record_to: recordings.jsonl}`.
"""

import json
from pathlib import Path

from metamorph.llm.base import LLMResult
from metamorph.llm.replay import recording_line
from metamorph.transforms import build_transform
from metamorph.transforms.llm import LLMRewrite, rewrite_request

HERE = Path(__file__).parent
TRANSFORMS: dict[str, LLMRewrite] = {
    "code_switch": build_transform("code_switch", {"style": "sheng"}),  # type: ignore[dict-item]
    "paraphrase": build_transform("paraphrase", {}),  # type: ignore[dict-item]
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
    (HERE / "recordings.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(lines)} recordings")


if __name__ == "__main__":
    main()
