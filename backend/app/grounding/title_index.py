"""SQLite (FTS5 or full-scan) + rapidfuzz ranked retrieval for KG entity names.

WHAT THIS MODULE DOES
----------------------
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

ONE FUNCTION, FOUR DIFFERENT MATCHING POLICIES (ADR-020)
------------------------------------------------------------
Course/book titles and university/department names are matched by different
rules, chosen from measurements against the real data (see ``_POLICY``
below and ADR-020 for the full numbers) — not from a preference for
uniformity:

  - **Scorer.** Titles are matched by ``token_sort_ratio`` (whole-phrase
    similarity); institutions are matched by ``WRatio`` (tolerant of a short
    partial mention inside a long label). Measured: a query naming one word
    of a multi-word university label scores >=90 under ``WRatio`` in 44/45
    cases, and under 90 in ALL 45 cases under ``token_sort_ratio`` (median
    53.8) — the scorer choice is not interchangeable between the two jobs.

  - **Candidate generation.** Course/book use FTS5 prefix search (tens of
    thousands of rows; a full scan would be slow). University/department use
    a full table scan (46 / 379 rows; an FTS5 index would be both unused —
    the 500-candidate budget can never bind — AND lossy, dropping 11% of true
    department matches that a full scan would find).

  - **Acronyms.** University search also consults the curated
    ``gazetteer.ACRONYM_MAP`` (ΑΠΘ, ΕΚΠΑ, ...) directly, because acronyms are
    unrankable by any scorer: stem-prefix retrieval finds only 2/15 of them,
    and ``WRatio`` scores only 2/15 above threshold. Without this,
    university search would fail on exactly the input Greek speakers type
    most often.

  - **Score floor.** Course/book keep any match with nonzero similarity
    (``score > 0``) — a fallback to Topic-stems in ``hints.py`` catches weak
    matches. University/department require ``score >= 90`` — the same
    constant ``linker.FUZZY_THRESHOLD`` uses, so a mention resolvable by
    Stage-1 grounding is resolvable here too, and vice versa.

TWO SEPARATE CORPORA PER TITLE CLASS, NOT ONE MERGED ONE
-------------------------------------------------------------
Course and book titles live in separate tables (``course``/``course_fts`` and
``book``/``book_fts`` — see ``schema.py``), each with its own
``_CANDIDATE_LIMIT``-sized candidate budget (see the ``ORDER BY bm25`` comment
inside ``_fts_candidates``, which explains why that budget has to be ordered
at all). A merged FTS index would split that budget across both corpora and
reintroduce the same truncation bug in a subtler form — one that only bites
when both corpora are dense in the same stem.

RANKER SEAM
-----------
This is the second ranking backend this module has had (the first was
TF-IDF cosine similarity, ADR-015; this one is ADR-018, extended to all four
entity classes by ADR-020). The public contract — ``TitleMatch``,
``rank_titles``, ``rank_titles_from_corpus`` — is unchanged across the swap,
so callers (``hints.py``) needed no changes.

CORPUS SOURCE
-------------
The committed SQLite database at ``backend/app/data/entities.db`` (see
``db.py``), built offline by ``backend/scripts/build_entity_db.py`` from a
live GraphDB SPARQL dump. If the database is missing, ``rank_titles`` raises
``FileNotFoundError`` with instructions to rebuild it (see ``db.get_connection``).

CONNECTIONS ARE NOT CACHED
---------------------------
Unlike the old TF-IDF version, there is no module-level index cache here.
Opening a SQLite connection and running an indexed (or, for the two small
classes, full-scan) query costs microseconds, so ``rank_titles`` opens a
fresh read-only connection per call and closes it before returning. This also
sidesteps the fact that a single ``sqlite3.Connection`` is not safe to share
across FastAPI's threadpool workers without extra locking.

For testing, use ``rank_titles_from_corpus(surface_map, phrase, k)`` which
builds a throwaway ``:memory:`` database from an explicit corpus dict and
bypasses ``entities.db`` entirely.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from app.grounding import db
from app.grounding.gazetteer import ACRONYM_MAP
from app.grounding.normalize import normalize_greek
from app.grounding.schema import (
    FTS_CLASSES,
    LISTABLE_CLASSES,
    TITLE_CLASSES,
    create_schema,
    sync_title_fts,
)
from app.grounding.stem import greek_stem

# ---------------------------------------------------------------------------
# Public data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TitleMatch:
    """A single ranked result from ``rank_titles``.

    Attributes
    ----------
    normalized_title : str
        The accent-free, lowercase key used for ranking (output of
        ``normalize_greek`` applied to the raw title/name).
    score : float
        Similarity score in the range [0, 1] (rapidfuzz's raw 0-100 score,
        divided by 100 — see ``_POLICY`` for which scorer produced it).
        Higher is better.
    surface_forms : list[str]
        All raw KG literal strings that normalize to ``normalized_title``.
        Includes both ALL-CAPS accent-free variants ("ΑΡΧΙΤΕΚΤΟΝΙΚΗ
        ΥΠΟΛΟΓΙΣΤΩΝ") and mixed-case accented variants ("Αρχιτεκτονική
        Υπολογιστών"), whichever are present in the KG. The caller should
        emit all of them in a SPARQL ``VALUES`` binding so the query matches
        regardless of how the title is stored.
    entity_class : str
        Which corpus this match came from — one of ``TITLE_CLASSES``.
        Trailing and defaulted so existing construction sites (before this
        field existed) still compile.
    parents : list[str]
        Parent university name(s), for ``entity_class == "department"``
        only. Sorted, deduplicated, non-empty when the department has any
        recorded parent — a department shared across several universities
        (joint programmes, or simply a common name like "ΠΛΗΡΟΦΟΡΙΚΗΣ") has
        more than one entry. Always ``[]`` for course/book/university.
    """

    normalized_title: str
    score: float
    surface_forms: list[str] = field(default_factory=list)
    entity_class: str = "course"
    parents: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-class matching policy (ADR-020)
# ---------------------------------------------------------------------------

# The shared threshold between this module's institution matching and
# linker.FUZZY_THRESHOLD (linker.py imports this constant rather than
# defining its own, so "resolvable by browsing" and "resolvable by Stage-1
# grounding" are guaranteed to mean the same score cutoff). 90.0 was chosen
# empirically (ADR-020 M4): against the real 46 university labels, a floor of
# 90 keeps 129/132 genuinely-matching queries and rejects all 1267/1267
# mismatched ones tried — moving to 85 keeps the same 129/132 with no
# precision gain, and going lower starts admitting false positives.
INSTITUTION_MATCH_THRESHOLD: float = 90.0


@dataclass(frozen=True)
class _MatchPolicy:
    """How one entity class is candidate-generated, scored, and filtered.

    See the module docstring "ONE FUNCTION, FOUR DIFFERENT MATCHING
    POLICIES" for the measurements behind each field.
    """

    scorer: Callable[..., float]  # a rapidfuzz scorer, e.g. fuzz.WRatio / fuzz.token_sort_ratio
    use_fts: bool          # FTS5 candidate generation, or a full table scan
    acronyms: bool          # also consult gazetteer.ACRONYM_MAP directly
    min_score: float        # raw 0-100 floor (see _clears_floor for the
                             # inclusive/exclusive distinction)
    inclusive_floor: bool   # True: score >= min_score. False: score > min_score.


_POLICY: dict[str, _MatchPolicy] = {
    "course": _MatchPolicy(
        scorer=fuzz.token_sort_ratio, use_fts=True, acronyms=False,
        min_score=0.0, inclusive_floor=False,
    ),
    "book": _MatchPolicy(
        scorer=fuzz.token_sort_ratio, use_fts=True, acronyms=False,
        min_score=0.0, inclusive_floor=False,
    ),
    "university": _MatchPolicy(
        scorer=fuzz.WRatio, use_fts=False, acronyms=True,
        min_score=INSTITUTION_MATCH_THRESHOLD, inclusive_floor=True,
    ),
    "department": _MatchPolicy(
        scorer=fuzz.WRatio, use_fts=False, acronyms=False,
        min_score=INSTITUTION_MATCH_THRESHOLD, inclusive_floor=True,
    ),
}

# Sanity check at import time: _POLICY's FTS classes must exactly match
# schema.FTS_CLASSES — the DDL generator and the ranker must agree on which
# classes have an FTS table, or one of them is silently wrong.
assert {name for name, p in _POLICY.items() if p.use_fts} == FTS_CLASSES
assert set(_POLICY) == set(TITLE_CLASSES)


def _clears_floor(score: float, policy: _MatchPolicy) -> bool:
    """Whether ``score`` (raw rapidfuzz 0-100) survives ``policy``'s floor.

    Course/book use an EXCLUSIVE floor at 0.0 — "any nonzero overlap" — the
    historic behaviour ``rank_titles`` has always had; a weak title match
    still falls back to Topic-stems in ``hints.py``. University/department
    use an INCLUSIVE floor at ``INSTITUTION_MATCH_THRESHOLD`` — ADR-020 M4
    measured the "correct" score distribution sitting with its median
    exactly AT 90.0, so an exclusive ``> 90`` would silently reject roughly
    half of genuine matches.
    """
    if policy.inclusive_floor:
        return score >= policy.min_score
    return score > policy.min_score


# ---------------------------------------------------------------------------
# Internal index state
# ---------------------------------------------------------------------------


@dataclass
class _IndexState:
    """Wraps the SQLite connection and target table ``_rank`` queries against.

    A thin wrapper (rather than passing a bare connection around) so the
    ranking seam documented above stays easy to swap again in the future.
    ``table`` is what makes this class-capable — the class currently being
    queried is exactly the kind of state this wrapper exists to carry.
    """

    conn: sqlite3.Connection
    table: str = "course"


# Maximum number of candidate titles the FTS5 stage hands to rapidfuzz, PER
# CLASS — course and book each get their own budget from their own separate
# FTS index (see "TWO SEPARATE CORPORA" in the module docstring). Only
# applies to FTS-backed classes (course, book); university/department scan
# their full (46 / 379 row) table instead — see ``_MatchPolicy.use_fts``.
_CANDIDATE_LIMIT = 500


# ---------------------------------------------------------------------------
# Index construction
# ---------------------------------------------------------------------------


def _build_index(
    surface_map: dict[str, list[str]],
    entity_class: str = "course",
    *,
    parent_map: dict[str, list[str]] | None = None,
) -> _IndexState:
    """Build a throwaway in-memory SQLite database from ``surface_map``.

    Pure with respect to the filesystem — never touches ``entities.db``. Used
    by ``rank_titles_from_corpus`` (tests) so tests are fully isolated from
    the live data and from each other.

    Args:
        surface_map: Mapping ``normalize_greek(title)`` -> ``[raw title, ...]``.
        entity_class: Which table to populate — one of ``TITLE_CLASSES``.
        parent_map: Optional mapping ``normalize_greek(name)`` -> ``[parent
                     university name, ...]``, for building a department
                     fixture. Every ``(surface, parent)`` pair under a given
                     ``norm`` becomes its own row — mirroring how a
                     department name shared by several universities is
                     several rows in the real database. Ignored (parent is
                     always NULL) for classes other than ``department``.

    Returns:
        An ``_IndexState`` wrapping the populated in-memory connection.

    Raises:
        ValueError: If ``entity_class`` is not a known title class.
    """
    if entity_class not in TITLE_CLASSES:
        raise ValueError(f"unknown title class {entity_class!r}; expected one of {TITLE_CLASSES}")

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema(conn)

    parent_map = parent_map or {}
    rows: list[tuple[str, str, str | None]] = []
    for norm, surfaces in surface_map.items():
        parents_for_norm = parent_map.get(norm, [])
        if parents_for_norm:
            rows.extend(
                (norm, surface, parent) for surface in surfaces for parent in parents_for_norm
            )
        else:
            rows.extend((norm, surface, None) for surface in surfaces)

    if rows:
        conn.executemany(
            f"INSERT INTO {entity_class}(norm, surface, parent) VALUES (?, ?, ?)", rows
        )
        if entity_class in FTS_CLASSES:
            sync_title_fts(conn, entity_class)
    conn.commit()

    return _IndexState(conn=conn, table=entity_class)


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def _fts_query_terms(phrase: str) -> list[str]:
    """Turn a normalized phrase into a list of FTS5 prefix-query stems.

    Each content word is reduced via ``greek_stem`` so inflected forms in the
    query (e.g. genitive "υπολογιστων") still match a differently-inflected
    title in the corpus (e.g. "ΥΠΟΛΟΓΙΣΤΕΣ"), because both share the same
    stem prefix. Duplicate stems are removed; empty stems are dropped. Only
    used for FTS-backed classes (course, book) — see ``_MatchPolicy.use_fts``.

    Args:
        phrase: An already ``normalize_greek``-processed phrase.

    Returns:
        A sorted list of distinct, non-empty stems. Sorted only for
        deterministic test output — order does not affect the OR query below.
    """
    tokens = phrase.split()
    stems = {greek_stem(t) for t in tokens}
    return sorted(s for s in stems if s)


def _fts_candidates(state: _IndexState, stems: list[str]) -> list[str]:
    """Stage 1 (FTS-backed classes only) — which titles share a stemmed word?

    High recall by design; precision comes from the rerank stage in
    ``_rank``. Deliberately high-recall/low-precision: a title needs only
    ONE stemmed word in common with the query to become a candidate.

    Args:
        state: An ``_IndexState`` whose ``table`` is in ``schema.FTS_CLASSES``.
        stems: Non-empty stem list from ``_fts_query_terms``.

    Returns:
        Up to ``_CANDIDATE_LIMIT`` distinct normalized titles, ordered by
        FTS5 relevance (see the ``ORDER BY bm25`` note below).
    """
    # Each stem becomes a quoted FTS5 prefix term ("term"*). Quoting protects
    # against stems that happen to collide with FTS5 query-syntax keywords
    # (e.g. a stem literally spelled "OR" or "NOT" would otherwise be parsed
    # as an operator rather than matched literally).
    fts_query = " OR ".join(f'"{stem}"*' for stem in stems)

    # SQL placeholders (?) can only substitute VALUES, never IDENTIFIERS —
    # SELECT * FROM ? is not valid SQL in any database, because the query
    # planner must know which table it's reading before it can plan anything.
    # A dynamic table name is therefore string interpolation by necessity;
    # `state.table` is checked against the closed TITLE_CLASSES tuple in `_rank` 
    # before this function is ever called, and this function is only reached for 
    # classes in FTS_CLASSES.
    # (`state.table` ultimately traces back to the `?class=` query param on
    # GET /entities/search — that guard is where the safety property has to
    # be enforced, in addition to the API layer's own validation.)
    if state.table not in TITLE_CLASSES:
            raise ValueError(f"unknown title class {state.table!r}; expected one of {TITLE_CLASSES}")
    table = state.table
    fts_table = f"{table}_fts"

    # ORDER BY bm25(...) is not optional. Common stems (e.g. "τεχνολογια"
    # alone matches ~1,500 distinct course titles; a real query's three
    # stems together matched 2,165) routinely exceed _CANDIDATE_LIMIT.
    # Without an ORDER BY, SQLite's LIMIT truncates to an ARBITRARY subset of
    # the matches, not the most relevant ones — a real user query for
    # "τεχνολογια βασεων δεδομενων" (a title that exists verbatim in the
    # corpus) returned zero results because the exact match fell outside the
    # arbitrary first 500 rows SQLite happened to return. bm25() ranks rows
    # by relevance to the MATCH (lower = better, hence ascending ORDER BY —
    # SQLite convention, not a bug); ordering before LIMIT guarantees
    # truncation drops the least relevant candidates first, never a
    # near-exact match. Verified empirically: the exact-match title above
    # ranks position 0 of 2,165 under this order. This applies per class —
    # see "TWO SEPARATE CORPORA" in the module docstring for why course and
    # book each get their own 500-slot budget instead of sharing one.
    cursor = state.conn.execute(
        f"SELECT DISTINCT c.norm "
        f"FROM {fts_table} f JOIN {table} c ON c.id = f.rowid "
        f"WHERE {fts_table} MATCH ? "
        f"ORDER BY bm25({fts_table}) "
        f"LIMIT ?",
        (fts_query, _CANDIDATE_LIMIT),
    )
    return [row["norm"] for row in cursor.fetchall()]


def _all_norms(state: _IndexState) -> list[str]:
    """Stage 1 (non-FTS classes only) — full scan of every distinct norm.

    university/department have no FTS table (see ``schema.FTS_CLASSES`` and
    the module docstring). At 46 / 379 distinct names, a full scan is both
    fast and — unlike FTS prefix retrieval at this row count — lossless
    (ADR-020 M2 measured FTS candidate coverage as low as 89% recall here).

    Args:
        state: An ``_IndexState`` whose ``table`` is NOT in ``FTS_CLASSES``.

    Returns:
        Every distinct normalized name in the table.
    """
    cursor = state.conn.execute(f"SELECT DISTINCT norm FROM {state.table}")
    return [row["norm"] for row in cursor.fetchall()]


def _lookup_surfaces_and_parents(state: _IndexState, norm: str) -> tuple[list[str], list[str]]:
    """Fetch every ``(surface, parent)`` row for one normalized name.

    ``DISTINCT`` matters here for reasons beyond deduplicating identical
    rows: a department name shared by several universities is several rows
    under the same ``norm`` — e.g. "ΠΛΗΡΟΦΟΡΙΚΗΣ" existing at four different
    institutions — and every distinct ``(surface, parent)`` pair must survive
    so ``parents`` reflects all of them.

    Args:
        state: An ``_IndexState`` wrapping an open connection.
        norm: A normalized name/title present in ``state.table``.

    Returns:
        ``(surface_forms, parents)`` — ``surface_forms`` sorted, ``parents``
        sorted and deduplicated with ``None`` entries dropped (always ``[]``
        for every class except ``department``).
    """
    rows = state.conn.execute(
        f"SELECT DISTINCT surface, parent FROM {state.table} WHERE norm = ? ORDER BY surface",
        (norm,),
    ).fetchall()
    surface_forms = [r["surface"] for r in rows]
    parents = sorted({r["parent"] for r in rows if r["parent"] is not None})
    return surface_forms, parents


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
        the policy's score floor are excluded — see ``_clears_floor``.
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
    # this class's scorer (see _POLICY / module docstring for why the scorer
    # differs by class).
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
    the duration of this call (see module docstring for why connections are
    not cached).

    Returns up to ``k`` results sorted by similarity (highest first, an
    acronym hit always first for ``entity_class="university"``). Returns
    ``[]`` if the phrase yields no usable candidates, or if no candidate
    clears the class's score floor (see ``_POLICY``).

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
                    for a ``department`` fixture — see ``_build_index``.

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
