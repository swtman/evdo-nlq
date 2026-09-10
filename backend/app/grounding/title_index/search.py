"""Ranked and exhaustive retrieval — the public entry points of this package.

WHAT THIS PACKAGE DOES
------------------------
Given a phrase extracted from a user question (e.g. "αρχιτεκτονικη υπολογιστων"
or "πανεπιστημιο πειραια"), ``rank_titles`` ranks one of four KG entity corpora
— course titles, book titles, university names, or department names — against
that phrase and returns the closest matching entities with a similarity score.

The caller (``hints.build_grounding_hints``) uses these matches to inject an
exact ``VALUES`` binding into the LLM system prompt, replacing an imprecise
single-stem ``CONTAINS`` filter that would otherwise apply. The ΟΝΤΟΛΟΓΙΑ
page's search cards (``GET /entities/search``, see ``api/entities.py``) call
the exact same function, so an entity found by browsing is guaranteed
matchable from a natural-language question — that guarantee is the entire
point of keeping one ranking function instead of two (ADR-018, ADR-020).

See ``policy.py`` for the four per-class matching policies this dispatches
on, and ``corpus.py`` for the SQLite access underneath.

RANKER SEAM
-----------
This is the second ranking backend this package has had (the first was
TF-IDF cosine similarity, ADR-015; this one is ADR-018, extended to all four
entity classes by ADR-020). The public contract — ``TitleMatch``,
``rank_titles``, ``rank_titles_from_corpus`` — is unchanged across the swap,
so callers (``hints.py``) needed no changes.
"""

from __future__ import annotations

from rapidfuzz import process

from app.grounding import db
from app.grounding.gazetteer import ACRONYM_MAP
from app.grounding.normalize import normalize_greek
from app.grounding.schema import LISTABLE_CLASSES, TITLE_CLASSES
from app.grounding.stem import greek_stem
from app.grounding.title_index.corpus import (
    _IndexState,
    _all_norms,
    _build_index,
    _fts_candidates,
    _lookup_surfaces_and_parents,
)
from app.grounding.title_index.policy import _POLICY, TitleMatch, _clears_floor

# ---------------------------------------------------------------------------
# FTS query-term construction
# ---------------------------------------------------------------------------


def _fts_query_terms(phrase: str) -> list[str]:
    """Turn a normalized phrase into a list of FTS5 prefix-query stems.

    Each content word is reduced via ``greek_stem`` so inflected forms in the
    query (e.g. genitive "υπολογιστων") still match a differently-inflected
    title in the corpus (e.g. "ΥΠΟΛΟΓΙΣΤΕΣ"), because both share the same
    stem prefix. Duplicate stems are removed; empty stems are dropped. Only
    used for FTS-backed classes (course, book) — see ``policy._MatchPolicy.use_fts``.

    Args:
        phrase: An already ``normalize_greek``-processed phrase.

    Returns:
        A sorted list of distinct, non-empty stems. Sorted only for
        deterministic test output — order does not affect the OR query below.
    """
    tokens = phrase.split()
    stems = {greek_stem(t) for t in tokens}
    return sorted(s for s in stems if s)


# ---------------------------------------------------------------------------
# Acronym matching (university only)
# ---------------------------------------------------------------------------


def _get_normalized_acronym_map() -> dict[str, str]:
    """Normalize ``gazetteer.ACRONYM_MAP`` keys once (module-level cache).

    A separate cache from ``linker._get_normalized_acronym_map`` — this
    module intentionally does not import from ``linker`` (the dependency
    direction is ``gazetteer -> title_index -> linker``, never the reverse),
    and the map is tiny (<20 entries) so the duplication costs nothing.
    """
    global _NORMALIZED_ACRONYM_MAP
    if _NORMALIZED_ACRONYM_MAP is None:
        _NORMALIZED_ACRONYM_MAP = {normalize_greek(k): v for k, v in ACRONYM_MAP.items()}
    return _NORMALIZED_ACRONYM_MAP


_NORMALIZED_ACRONYM_MAP: dict[str, str] | None = None


def _acronym_match(state: _IndexState, q_norm: str) -> TitleMatch | None:
    """Direct lookup against ``gazetteer.ACRONYM_MAP`` (university only).

    Acronyms are unrankable by any scorer — ADR-020 M3 measured only 2/15
    entries retrievable by FTS stem-prefix and only 2/15 scoring >=90 under
    WRatio — so ΑΠΘ, ΕΚΠΑ, etc. must be resolved by direct dictionary lookup,
    not left to ``_rank``'s candidate generation + scoring pipeline.

    Args:
        state: An ``_IndexState`` for the ``university`` table.
        q_norm: The already-normalized query phrase.

    Returns:
        A ``TitleMatch`` with ``score=1.0`` if ``q_norm`` is a known acronym
        AND its canonical label is present in the live database, else
        ``None`` (a stale ``ACRONYM_MAP`` entry pointing at a label the KG
        no longer has is treated as no match, not an error).
    """
    canonical = _get_normalized_acronym_map().get(q_norm)
    if canonical is None:
        return None
    target_norm = normalize_greek(canonical)
    surface_forms, parents = _lookup_surfaces_and_parents(state, target_norm)
    if not surface_forms:
        return None
    return TitleMatch(
        normalized_title=target_norm,
        score=1.0,
        surface_forms=surface_forms,
        entity_class=state.table,
        parents=parents,
    )


# ---------------------------------------------------------------------------
# Ranking orchestration
# ---------------------------------------------------------------------------


def _rank(phrase: str, k: int, state: _IndexState) -> list[TitleMatch]:
    """Rank corpus entries against ``phrase`` per ``state.table``'s ``_MatchPolicy``.

    Pure function of ``state`` — takes an explicit ``_IndexState`` so it works
    identically for the live ``rank_titles`` (real ``entities.db`` connection)
    and the test helper ``rank_titles_from_corpus`` (in-memory connection).

    Args:
        phrase: Raw user phrase to rank against the corpus. Normalized
                internally before matching.
        k: Maximum number of results to return.
        state: An ``_IndexState`` wrapping an open, schema-initialized
               SQLite connection.

    Returns:
        List of up to ``k`` ``TitleMatch`` objects sorted by score descending
        (an acronym hit, if any, is always first). Matches that don't clear
        the policy's score floor are excluded — see ``policy._clears_floor``.
    """
    if state.table not in TITLE_CLASSES:
        raise ValueError(f"unknown title class {state.table!r}; expected one of {TITLE_CLASSES}")

    policy = _POLICY[state.table]

    q_norm = normalize_greek(phrase)
    if not q_norm:
        return []

    acronym_hit = _acronym_match(state, q_norm) if policy.acronyms else None

    if policy.use_fts:
        stems = _fts_query_terms(q_norm)
        candidate_norms = _fts_candidates(state, stems) if stems else []
    else:
        candidate_norms = _all_norms(state)

    # Stage 2 — rerank: score every candidate against the full phrase with
    # this class's scorer (see policy._POLICY / package docstring for why
    # the scorer differs by class).
    results: list[TitleMatch] = []
    if candidate_norms:
        ranked = process.extract(q_norm, candidate_norms, scorer=policy.scorer, limit=k)
        for norm, score, _idx in ranked:
            if not _clears_floor(score, policy):
                continue
            surface_forms, parents = _lookup_surfaces_and_parents(state, norm)
            results.append(
                TitleMatch(
                    normalized_title=norm,
                    score=score / 100.0,
                    surface_forms=surface_forms,
                    entity_class=state.table,
                    parents=parents,
                )
            )

    if acronym_hit is not None:
        results = [r for r in results if r.normalized_title != acronym_hit.normalized_title]
        results.insert(0, acronym_hit)
        results = results[:k]

    return results


# ---------------------------------------------------------------------------
# Public API — ranked search
# ---------------------------------------------------------------------------


def rank_titles(phrase: str, k: int = 3, *, entity_class: str = "course") -> list[TitleMatch]:
    """Rank a KG entity corpus against ``phrase``.

    Opens a fresh, read-only connection to the committed ``entities.db`` for
    the duration of this call (see ``corpus.py`` for why connections are
    not cached).

    Returns up to ``k`` results sorted by similarity (highest first, an
    acronym hit always first for ``entity_class="university"``). Returns
    ``[]`` if the phrase yields no usable candidates, or if no candidate
    clears the class's score floor (see ``policy._POLICY``).

    Args:
        phrase: Raw content phrase from the user question (after entity and
                stopword tokens have been removed), e.g.
                "αρχιτεκτονικη υπολογιστων" or "πανεπιστημιο πειραια".
                Accents and casing are normalized internally.
        k: Maximum number of ranked candidates to return. Default 3.
        entity_class: Which corpus to search — one of ``TITLE_CLASSES``
                      (``"course"`` (default), ``"book"``, ``"university"``,
                      ``"department"``). Keyword-only so a bare third
                      positional argument (an easy mix-up with ``k``) can't
                      happen, and defaulted so every existing call site is
                      unaffected.

    Returns:
        List of ``TitleMatch`` objects sorted by score descending, length 0..k.
        Each match's ``entity_class`` equals the ``entity_class`` argument.

    Raises:
        FileNotFoundError: If ``entities.db`` is missing. See ``db.get_connection``.
        ValueError: If ``entity_class`` is not a known title class.
    """
    conn = db.get_connection()
    try:
        return _rank(phrase, k, _IndexState(conn=conn, table=entity_class))
    finally:
        conn.close()


def rank_titles_from_corpus(
    surface_map: dict[str, list[str]],
    phrase: str,
    k: int = 3,
    *,
    entity_class: str = "course",
    parent_map: dict[str, list[str]] | None = None,
) -> list[TitleMatch]:
    """Rank titles from an explicit corpus dict (for unit tests).

    Identical to ``rank_titles`` but builds a fresh in-memory database from
    ``surface_map`` instead of reading ``entities.db``. Fully isolated from
    the live data and from other tests.

    Args:
        surface_map: A ``normalize_greek(title)`` -> ``[raw surface form, ...]``
                     dict. Typically a small fixture corpus.
        phrase: Raw user phrase to rank.
        k: Maximum number of results.
        entity_class: Which table to build/query — one of ``TITLE_CLASSES``.
                      Lets a test build a department fixture and assert the
                      ranker treats it under the institution policy.
        parent_map: Optional ``normalize_greek(name) -> [parent, ...]`` dict
                    for a ``department`` fixture — see ``corpus._build_index``.

    Returns:
        List of ``TitleMatch`` objects sorted by score descending.

    Raises:
        ValueError: If ``entity_class`` is not a known title class.
    """
    state = _build_index(surface_map, entity_class, parent_map=parent_map)
    try:
        return _rank(phrase, k, state)
    finally:
        state.conn.close()


# ---------------------------------------------------------------------------
# Public API — exhaustive listing (university, department)
# ---------------------------------------------------------------------------


def list_titles(*, entity_class: str, limit: int = 1000) -> list[TitleMatch]:
    """Return every entry of a small, listable corpus, alphabetically.

    This is NOT a ranking function — there is no query phrase, no scorer, no
    candidate generation. It backs ``GET /entities/list`` (the "δείτε τα όλα"
    browse tier for the University/Department ΟΝΤΟΛΟΓΙΑ cards), which is a
    genuinely different job from search: "show me everything" has no
    meaningful "similarity to what?" to rank against. Restricted to
    ``LISTABLE_CLASSES`` — course (~73k) and book (~37k) are far too large to
    ever meaningfully "list"; use ``rank_titles`` for those.

    Args:
        entity_class: One of ``schema.LISTABLE_CLASSES`` (``"university"`` or
                      ``"department"``).
        limit: Maximum number of entries to return. Default 1000 — enough
               for all 799 department rows (≈379 distinct names) in one call.

    Returns:
        Every distinct name in the class, alphabetically, each as a
        ``TitleMatch`` with ``score=1.0`` (listing implies no similarity
        judgement) and ``surface_forms``/``parents`` populated exactly as
        ``rank_titles`` would populate them.

    Raises:
        ValueError: If ``entity_class`` is not in ``LISTABLE_CLASSES``.
        FileNotFoundError: If ``entities.db`` is missing.
    """
    if entity_class not in LISTABLE_CLASSES:
        raise ValueError(
            f"unknown listable class {entity_class!r}; expected one of {LISTABLE_CLASSES}"
        )

    conn = db.get_connection()
    try:
        state = _IndexState(conn=conn, table=entity_class)
        # One grouping query to get the distinct normalized names in
        # alphabetical order (by a representative surface form), then reuse
        # the same per-norm surface/parent lookup `_rank` uses per match.
        rows = state.conn.execute(
            f"SELECT norm FROM {entity_class} GROUP BY norm ORDER BY MIN(surface) LIMIT ?",
            (limit,),
        ).fetchall()
        results: list[TitleMatch] = []
        for row in rows:
            surface_forms, parents = _lookup_surfaces_and_parents(state, row["norm"])
            results.append(
                TitleMatch(
                    normalized_title=row["norm"],
                    score=1.0,
                    surface_forms=surface_forms,
                    entity_class=entity_class,
                    parents=parents,
                )
            )
        return results
    finally:
        conn.close()
