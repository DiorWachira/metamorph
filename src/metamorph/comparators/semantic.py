"""Meaning-level comparators: local embeddings and an LLM entailment judge."""

from __future__ import annotations

import asyncio
import math
from collections.abc import Callable, Sequence
from typing import Any

from metamorph.comparators.base import Comparator, register
from metamorph.errors import ConfigError, NotComparable
from metamorph.llm.base import LLMError, LLMRequest
from metamorph.llm.service import LLMService
from metamorph.services import Services
from metamorph.types import Comparison

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
Embedder = Callable[[list[str]], Sequence[Sequence[float]]]
_MODELS: dict[str, Embedder] = {}


def fastembed_embedder(model: str) -> Embedder:
    """A CPU ONNX embedder (no torch). Loaded once per process; the model downloads on first use."""
    if model not in _MODELS:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise ConfigError(
                "embedding_similarity needs fastembed: pip install 'metamorph[embeddings]'"
            ) from exc
        engine = TextEmbedding(model_name=model)
        _MODELS[model] = lambda texts: [list(map(float, v)) for v in engine.embed(texts)]
    return _MODELS[model]


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm = math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b))
    return dot / norm if norm else 0.0


@register
class EmbeddingSimilarity(Comparator):
    """Cosine similarity of sentence embeddings, clipped to [0, 1]."""

    name = "embedding_similarity"
    default_threshold = 0.85

    def __init__(
        self, model: str = DEFAULT_EMBEDDING_MODEL, embedder: Embedder | None = None
    ) -> None:
        self.model = model
        self._embedder = embedder
        self._vectors: dict[str, Sequence[float]] = {}

    def _embed(self, texts: list[str]) -> list[Sequence[float]]:
        missing = [t for t in dict.fromkeys(texts) if t not in self._vectors]
        if missing:
            embedder = self._embedder or fastembed_embedder(self.model)
            self._vectors.update(zip(missing, embedder(missing), strict=True))
        return [self._vectors[t] for t in texts]

    def compare(self, a: str, b: str) -> Comparison:
        if not a.strip() and not b.strip():
            return Comparison(1.0, "both empty")
        va, vb = self._embed([a, b])
        score = max(0.0, min(1.0, cosine(va, vb)))
        return Comparison(score, f"cosine {score:.2f}")

    async def acompare(self, a: str, b: str) -> Comparison:
        return await asyncio.to_thread(self.compare, a, b)  # ONNX inference is CPU-bound


JUDGE_SYSTEM = (
    "You judge whether two outputs of the same AI application give the same answer. Output A "
    "answered the original input; output B answered a variant that should have the same answer. "
    "They may differ in wording, order, length or language. Reply with JSON only."
)
JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["ENTAILS", "CONTRADICTS", "NEUTRAL"]},
        "reason": {"type": "string"},
    },
    "required": ["verdict", "reason"],
    "additionalProperties": False,
}
VERDICT_SCORES = {"ENTAILS": 1.0, "NEUTRAL": 0.5, "CONTRADICTS": 0.0}


def judge_request(a: str, b: str) -> LLMRequest:
    prompt = (
        f"Output A:\n<<<\n{a}\n>>>\n\nOutput B:\n<<<\n{b}\n>>>\n\n"
        "ENTAILS: B gives the same answer as A. CONTRADICTS: B gives a different or incompatible "
        "answer. NEUTRAL: B neither confirms nor contradicts A (for example it omits the key "
        "information). Give a one-line reason."
    )
    return LLMRequest(system=JUDGE_SYSTEM, prompt=prompt, schema=JUDGE_SCHEMA, max_tokens=512)


@register
class Entails(Comparator):
    """LLM judge: ENTAILS = 1.0, NEUTRAL = 0.5, CONTRADICTS = 0.0. Works across languages."""

    name = "entails"
    default_threshold = 0.75

    def __init__(self) -> None:
        self.llm: LLMService | None = None

    def bind(self, services: Services) -> None:
        self.llm = services.require_llm("comparator 'entails'")

    def compare(self, a: str, b: str) -> Comparison:
        raise TypeError("entails is LLM-backed; the judge calls acompare")

    async def acompare(self, a: str, b: str) -> Comparison:
        if self.llm is None:
            raise NotComparable("entails was not bound to a helper model")
        if a.strip() == b.strip():
            return Comparison(1.0, "identical outputs")  # no need to pay for a judge call
        try:
            data: dict[str, Any] = await self.llm.complete_json(
                "judge:entails", judge_request(a, b)
            )
        except LLMError as exc:
            raise NotComparable(f"judge unavailable: {exc}") from exc
        verdict = str(data.get("verdict", "")).upper()
        if verdict not in VERDICT_SCORES:
            raise NotComparable(f"judge returned an unknown verdict {verdict!r}")
        return Comparison(VERDICT_SCORES[verdict], f"{verdict}: {data.get('reason', '')}".strip())
