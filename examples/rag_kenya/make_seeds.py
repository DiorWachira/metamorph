"""Regenerate seeds.jsonl: each question with the chunks the app retrieves for it.

Storing the retrieved chunks in the seed lets Metamorph perturb the context (reorder it, add a
distractor) and send it back through the app's context-injection input.
"""

import json
from pathlib import Path

from rag_app import retrieve

QUESTIONS = {
    "constitution-date": "When was the Constitution of Kenya promulgated?",
    "counties": "How many counties did the 2010 constitution create?",
    "official-languages": "Which languages are official languages under Article 7?",
    "mpesa-launch": "When did Safaricom launch M-Pesa?",
    "mpesa-agents": "Wanjiru asks: what do M-Pesa agents do with cash?",
    "sgr-length": "How many kilometres long is the Mombasa-Nairobi railway line?",
    "sgr-opening": "When did the Madaraka Express passenger service open?",
    "batian-height": "Which peak of Mount Kenya rises to 5199 metres?",
    "first-park": "Which was the first national park, established in 1946?",
    "park-size": "Kamau wants to know how large Nairobi National Park is in square kilometres.",
    "odpc": "Which office did the Data Protection Act establish?",
    "independence": "On what date did Kenya become independent from Britain?",
    "first-president": "Who became the first President when Kenya became a republic?",
    "turkana": "What is special about Lake Turkana among desert lakes?",
    "vision-pillars": "What are the three pillars of Kenya Vision 2030?",
}


def main() -> None:
    out = Path(__file__).parent / "seeds.jsonl"
    with out.open("w", encoding="utf-8") as f:
        for seed_id, question in QUESTIONS.items():
            row = {
                "id": seed_id,
                "tags": ["rag", "en"],
                "input": {"question": question, "documents": retrieve(question)},
            }
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"wrote {len(QUESTIONS)} seeds to {out}")


if __name__ == "__main__":
    main()
