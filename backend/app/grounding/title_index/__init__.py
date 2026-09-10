"""SQLite (FTS5 or full-scan) + rapidfuzz ranked retrieval for KG entity names.

This is a package, split (2026-09) out of a single ``title_index.py`` along
its one real internal seam: SQLite access vs. matching policy vs. the public
API that ties them together.

    policy.py    Per-class matching policy — ``TitleMatch``, ``_MatchPolicy``,
                 ``_POLICY``, ``INSTITUTION_MATCH_THRESHOLD``. Pure data, no I/O.
    corpus.py    Every SQLite statement — connection state, FTS5 candidate
                 generation, full-table scan, row hydration, and the
                 in-memory test-fixture builder.
    search.py    Orchestration and the three public entry points:
                 ``rank_titles``, ``rank_titles_from_corpus``, ``list_titles``.

See ADR-021 for why the split happened and why it takes this particular
shape. The public contract is unchanged: every name below resolved from
``app.grounding.title_index`` before the split and still does.
"""

from __future__ import annotations

from app.grounding.title_index.corpus import _build_index  # noqa: F401 — re-exported for tests
from app.grounding.title_index.policy import INSTITUTION_MATCH_THRESHOLD, TitleMatch
from app.grounding.title_index.search import _rank  # noqa: F401 — re-exported for tests
from app.grounding.title_index.search import (
    list_titles,
    rank_titles,
    rank_titles_from_corpus,
)

__all__ = [
    "INSTITUTION_MATCH_THRESHOLD",
    "TitleMatch",
    "list_titles",
    "rank_titles",
    "rank_titles_from_corpus",
]
