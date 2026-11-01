"""Comparators: (source output, follow-up output) -> agreement score. Importing registers them."""

from metamorph.comparators import labels, numeric, semantic, structured, text
from metamorph.comparators.base import Comparator, build_comparator

__all__ = [
    "Comparator",
    "build_comparator",
    "labels",
    "numeric",
    "semantic",
    "structured",
    "text",
]
