"""Loads and caches the gold few-shot example bank from prompts/examples.yaml.

Exposes select_few_shot() which renders N examples into a text block suitable
for injection into the {few_shot_block} placeholder in nl-to-sparql-v2.md.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_EXAMPLES_PATH = Path(__file__).parent.parent.parent.parent / "prompts" / "examples.yaml"

# Module-level cache — populated on first load, reused for process lifetime.
_cache: list[dict[str, Any]] | None = None

# Shape priority order for few-shot selection (lower = higher priority).
# Derived from few_shot_priority field in examples.yaml; kept here as a fallback.
_SHAPE_ORDER = [
    "traversal-lookup",
    "negative-existence",
    "multi-level-aggregate-with-concat",
    "set-difference-by-year",
    "set-difference-by-book",
    "set-intersection-by-book",
    "multi-level-count",
    "multi-book-comparison",
    "ranking-by-count",
    "not-answerable",
]

REQUIRED_FIELDS = {
    "id",
    "question_english",
    "question_greek",
    "gold_sparql",
    "query_shape",
    "granularity",
    "comparison_mode",
}


def load_examples() -> list[dict[str, Any]]:
    """Return all examples from examples.yaml (cached after first read)."""
    global _cache
    if _cache is not None:
        return _cache

    if not _EXAMPLES_PATH.exists():
        raise FileNotFoundError(f"Examples file not found: {_EXAMPLES_PATH}")

    raw = yaml.safe_load(_EXAMPLES_PATH.read_text(encoding="utf-8"))
    examples: list[dict[str, Any]] = raw.get("examples", [])

    for ex in examples:
        missing = REQUIRED_FIELDS - ex.keys()
        if missing:
            raise ValueError(f"Example {ex.get('id', '?')} missing fields: {missing}")

    _cache = examples
    logger.info("Loaded %d examples from %s", len(examples), _EXAMPLES_PATH.name)
    return _cache


def select_few_shot(k: int = 8, *, include_not_answerable: bool = True) -> str:
    """Return a rendered few-shot text block with up to k examples.

    Selects one example per distinct query_shape, ordered by few_shot_priority
    (ascending). Examples with skip_eval=True or containing 'TODO' in NL fields
    are still included (they are valid structural examples). NOT_ANSWERABLE
    examples are included unless include_not_answerable=False.

    The returned string is ready to substitute into {few_shot_block}.
    """
    examples = load_examples()

    # Filter out examples marked as skip for few-shot (extremely high priority)
    candidates = [
        ex for ex in examples
        if ex.get("query_shape") != "not-answerable" or include_not_answerable
    ]

    # Deduplicate by shape: keep the lowest few_shot_priority per shape.
    seen_shapes: dict[str, dict[str, Any]] = {}
    for ex in sorted(candidates, key=lambda e: e.get("few_shot_priority", 99)):
        shape = ex["query_shape"]
        if shape not in seen_shapes:
            seen_shapes[shape] = ex

    # Sort selected examples by shape order, then by few_shot_priority.
    selected = sorted(
        seen_shapes.values(),
        key=lambda e: (
            _SHAPE_ORDER.index(e["query_shape"])
            if e["query_shape"] in _SHAPE_ORDER
            else 99,
            e.get("few_shot_priority", 99),
        ),
    )[:k]

    return _render_block(selected)


def _render_block(examples: list[dict[str, Any]]) -> str:
    """Render a list of examples into a formatted text block for prompt injection."""
    parts: list[str] = []
    for i, ex in enumerate(examples, 1):
        shape = ex["query_shape"]
        gran = ex.get("granularity", "n/a")
        label = f"{shape} ({gran})" if gran != "n/a" else shape
        sparql = ex["gold_sparql"].strip()
        q_en = ex["question_english"].strip()
        q_gr = ex["question_greek"].strip()
        block = (
            f"### Example {i} — {label}\n"
            f"Question (Greek): {q_gr}\n"
            f"Question (English): {q_en}\n"
            f"SPARQL:\n{sparql}"
        )
        parts.append(block)

    return "\n\n".join(parts)
