"""A tiny RAG app over public facts about Kenya, with a planted bug for Metamorph to find.

Retrieval is TF-IDF over the files in corpus/. Generation is a deterministic extractive stand-in
for an LLM: it answers with the context sentence that best overlaps the question.

The planted bug: the generator reads only the FIRST retrieved chunk. Answers look right
whenever retrieval ranks the relevant chunk first, so ordinary example-based tests pass, but
the answer changes when the same chunks arrive in a different order. Metamorph's
doc-order-invariance relation catches it. Set RAG_FIXED=1 to run the corrected version.

Run as a server:  uvicorn rag_app:api --port 8765
"""

from __future__ import annotations

import os
import re
from functools import cache
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

CORPUS = Path(__file__).parent / "corpus"
TOP_K = 3
STOPWORDS = frozenset(
    re.findall(
        r"\w+",
        """a an and are as at be by did does for from has have how in is it its of on or the to
        was what when where which who why with kenya kenyan""",
    )
)


@cache
def _index() -> tuple[list[str], TfidfVectorizer, object]:
    chunks = [p.read_text(encoding="utf-8").strip() for p in sorted(CORPUS.glob("*.md"))]
    vectorizer = TfidfVectorizer(stop_words="english")
    return chunks, vectorizer, vectorizer.fit_transform(chunks)


def retrieve(question: str, k: int = TOP_K) -> list[str]:
    chunks, vectorizer, matrix = _index()
    scores = linear_kernel(vectorizer.transform([question]), matrix).ravel()
    ranked = sorted(range(len(chunks)), key=lambda i: (-scores[i], i))
    return [chunks[i] for i in ranked[:k]]


def _terms(text: str) -> set[str]:
    return {t for t in re.findall(r"\w+", text.lower()) if t not in STOPWORDS}


def generate(question: str, documents: list[str]) -> str:
    fixed = os.environ.get("RAG_FIXED") == "1"
    context = documents if fixed else documents[:1]  # <- the planted bug
    sentences = [s for doc in context for s in re.split(r"(?<=[.!?])\s+", doc) if s]
    if not sentences:
        return "I don't know."
    terms = _terms(question)
    # Ties break on the sentence text, never on position, so the order of context is irrelevant.
    return max(sentences, key=lambda s: (len(terms & _terms(s)), s))


def answer(payload: dict) -> dict:
    """Python-callable entry point. Pass `documents` to bypass retrieval (context injection)."""
    question = payload["question"]
    documents = payload.get("documents") or retrieve(question)
    return {"answer": generate(question, documents), "documents": documents}


class Question(BaseModel):
    question: str
    documents: list[str] | None = None


api = FastAPI(title="rag-kenya")


@api.post("/answer")
def answer_endpoint(body: Question) -> dict:
    return answer(body.model_dump())
