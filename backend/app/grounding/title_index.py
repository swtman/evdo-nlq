"""SQLite FTS5 + rapidfuzz ranked retrieval for course/book titles.

WHAT THIS MODULE DOES
----------------------
Given a phrase extracted from a user question (e.g. "αρχιτεκτονικη υπολογιστων"),
``rank_titles`` ranks a real KG title corpus — course titles by default, or
book titles via ``entity_class="book"`` — against that phrase and returns the
closest matching title(s) with a similarity score.

The caller (``hints.build_grounding_hints``) uses these matches to inject an
exact ``VALUES ?title { "..." }`` binding into the LLM system prompt, replacing
the imprecise single-stem ``CONTAINS`` filter that would otherwise apply.

TWO SEPARATE CORPORA, NOT ONE MERGED ONE
-------------------------------------------
Course and book titles live in separate tables (``course``/``course_fts`` and
``book``/``book_fts`` — see ``schema.py``), each with its own
``_CANDIDATE_LIMIT``-sized candidate budget (see the ``ORDER BY bm25`` comment
inside ``_rank``, which explains why that budget has to be ordered at all). A
merged FTS index would split that budget across both corpora and reintroduce
the same truncation bug in a subtler form — one that only bites when both
corpora are dense in the same stem (ADR-019).

TWO-STAGE RANKING (candidate generation, then rerank)
-------------------------------------------------------
Comparing the query phrase against all ~73,000 course titles one at a time is
too slow to do on every request (this module used to fit a TF-IDF vectorizer
over the whole corpus on first use — a ~5-6 second one-time cost; see
ADR-018). Instead:

  1. **Candidate generation (SQLite FTS5).** Each content word of the query is
     reduced to a stem via ``greek_stem`` (e.g. "υπολογιστων" -> "υπολογιστ")
     and turned into an FTS5 *prefix* query term (``"υπολογιστ"*``). The terms
     are OR'd together, so a title needs to share just ONE stemmed word with
     the query to become a candidate — this stage is deliberately high-recall,
     not high-precision. It narrows the corpus (~73,000 course titles, or
     ~37,000 book titles) down to at most ``_CANDIDATE_LIMIT`` (500,
     *per class*) candidate titles in well under a millisecond, because FTS5
     looks the stem up in an index instead of scanning every title.

  2. **Rerank (rapidfuzz).** ``rapidfuzz.fuzz.token_sort_ratio`` scores each
     candidate against the full query phrase. This is where precision comes
     from: a title that matches every word of the phrase scores far higher
     than one that only shares a single word, so "αρχιτεκτονική υπολογιστών"
     outranks "αρχιτεκτονική τοπίου" for the query "αρχιτεκτονικη
     υπολογιστων" even though stage 1 returns both as candidates.

     WHY ``token_sort_ratio`` AND NOT ``WRatio``?
       ``linker.py`` uses ``fuzz.WRatio`` for university/department matching,
       and it is tempting to reuse it here for consistency. But ``WRatio``
       is deliberately lenient toward *partial* matches — it is designed so
       that a short user mention ("ΑΠΘ") scores high against a long
       canonical name it is a fragment of ("ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ
       ΘΕΣ/ΝΙΚΗΣ"). That is exactly the wrong behaviour for title
       resolution: with ``WRatio``, the single generic word "αλγορίθμων"
       ("algorithms") scores 90/100 against the specific course "Ανάλυση
       και Σχεδίαση Αλγορίθμων" ("Algorithm Analysis and Design") purely
       because it is a substring fragment of it — even though the user
       named a topic, not that course. ``token_sort_ratio`` instead
       measures whole-string similarity (after sorting each string's words,
       so word order does not matter): the same pair scores 48.8/100,
       correctly falling below ``settings.course_match_threshold``, while a
       genuine full-phrase match in a different inflection ("υπολογιστου"
       vs. "υπολογιστων") still scores 92/100. Verified against the real
       corpus while implementing this module — see ADR-018.

RANKER SEAM
-----------
This is the second ranking backend this module has had (the first was
TF-IDF cosine similarity, ADR-015; this one is ADR-018). The public contract —
``TitleMatch``, ``rank_titles``, ``rank_titles_from_corpus`` — is unchanged
across the swap, so callers (``hints.py``) needed no changes.

CORPUS SOURCE
-------------
The committed SQLite database at ``backend/app/data/entities.db`` (see
``db.py``), built offline by ``backend/scripts/build_entity_db.py`` from a
live GraphDB SPARQL dump. If the database is missing, ``rank_titles`` raises
``FileNotFoundError`` with instructions to rebuild it (see ``db.get_connection``).

CONNECTIONS ARE NOT CACHED
---------------------------
Unlike the old TF-IDF version, there is no module-level index cache here.
Opening a SQLite connection and running an indexed query costs microseconds,
so ``rank_titles`` opens a fresh read-only connection per call and closes it
before returning. This also sidesteps the fact that a single
``sqlite3.Connection`` is not safe to share across FastAPI's threadpool
workers without extra locking.

For testing, use ``rank_titles_from_corpus(surface_map, phrase, k)`` which
builds a throwaway ``:memory:`` database from an explicit corpus dict and
bypasses ``entities.db`` entirely.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from app.grounding import db
from app.grounding.normalize import normalize_greek
from app.grounding.schema import TITLE_CLASSES, create_schema, sync_title_fts
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
        ``normalize_greek`` applied to the raw title).
    score : float
        Similarity score in the range [0, 1] (rapidfuzz's WRatio, which is
        0-100, divided by 100). Higher is better.
    surface_forms : list[str]
        All raw KG title strings that normalize to ``normalized_title``.
        Includes both ALL-CAPS accent-free variants ("ΑΡΧΙΤΕΚΤΟΝΙΚΗ
        ΥΠΟΛΟΓΙΣΤΩΝ") and mixed-case accented variants ("Αρχιτεκτονική
        Υπολογιστών"), whichever are present in the KG. The caller should
        emit all of them in a SPARQL ``VALUES`` binding so the query matches
        regardless of how the title is stored.
    entity_class : str
        Which corpus this match came from — ``"course"`` or ``"book"``.
        Trailing and defaulted so existing construction sites (before this
        field existed) still compile. Needed once a caller (``hints.py``)
        ranks both corpora and merges the two result lists — at that point
        provenance is only recoverable if it travels on the object itself.
    """

    normalized_title: str
    score: float
    surface_forms: list[str] = field(default_factory=list)
    entity_class: str = "course"


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


# Maximum number of candidate titles stage 1 (FTS5) hands to stage 2
# (rapidfuzz), PER CLASS — course and book each get their own budget from
# their own separate FTS index (see "TWO SEPARATE CORPORA" in the module
# docstring). Large enough that a true match is essentially never excluded
# (in practice a shared stem word narrows tens of thousands of titles to low
# hundreds), small enough that rapidfuzz's per-candidate scoring stays well
# under a millisecond.
_CANDIDATE_LIMIT = 500


# ---------------------------------------------------------------------------
# Index construction
# ---------------------------------------------------------------------------


def _build_index(surface_map: dict[str, list[str]], entity_class: str = "course") -> _IndexState:
    """Build a throwaway in-memory SQLite database from ``surface_map``.

    Pure with respect to the filesystem — never touches ``entities.db``. Used
    by ``rank_titles_from_corpus`` (tests) so tests are fully isolated from
    the live data and from each other.

    Args:
        surface_map: Mapping ``normalize_greek(title)`` -> ``[raw title, ...]``.
        entity_class: Which table to populate — one of ``TITLE_CLASSES``.

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

    rows = [
        (norm, surface)
        for norm, surfaces in surface_map.items()
        for surface in surfaces
    ]
    if rows:
        conn.executemany(
            f"INSERT INTO {entity_class}(norm, surface) VALUES (?, ?)", rows
        )
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
    stem prefix. Duplicate stems are removed; empty stems are dropped.

    Args:
        phrase: An already ``normalize_greek``-processed phrase.

    Returns:
        A sorted list of distinct, non-empty stems. Sorted only for
        deterministic test output — order does not affect the OR query below.
    """
    tokens = phrase.split()
    stems = {greek_stem(t) for t in tokens}
    return sorted(s for s in stems if s)


def _rank(phrase: str, k: int, state: _IndexState) -> list[TitleMatch]:
    """Rank corpus titles against ``phrase`` via FTS5 candidates + rapidfuzz rerank.

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
        List of up to ``k`` ``TitleMatch`` objects sorted by score descending.
        Titles with score 0.0 are excluded (no meaningful overlap at all).
    """
    if state.table not in TITLE_CLASSES:
        raise ValueError(f"unknown title class {state.table!r}; expected one of {TITLE_CLASSES}")

    q_norm = normalize_greek(phrase)
    if not q_norm:
        return []

    stems = _fts_query_terms(q_norm)
    if not stems:
        return []

    # Each stem becomes a quoted FTS5 prefix term ("term"*). Quoting protects
    # against stems that happen to collide with FTS5 query-syntax keywords
    # (e.g. a stem literally spelled "OR" or "NOT" would otherwise be parsed
    # as an operator rather than matched literally).
    fts_query = " OR ".join(f'"{stem}"*' for stem in stems)

    # SQL placeholders (?) can only substitute VALUES, never IDENTIFIERS —
    # SELECT * FROM ? is not valid SQL in any database, because the query
    # planner must know which table it's reading before it can plan anything.
    # A dynamic table name is therefore string interpolation by necessity;
    # what makes it safe here is that `state.table` is checked against the
    # closed TITLE_CLASSES tuple immediately above, never used un-guarded.
    # (`state.table` ultimately traces back to the `?class=` query param on
    # GET /entities/search — this guard is the layer that actually touches
    # SQL, so it's where the safety property has to be enforced, in addition
    # to the API layer's own validation.)
    table = state.table
    fts_table = f"{table}_fts"

    # Stage 1 — candidate generation: which titles share at least one
    # stemmed word with the query? High recall by design; precision comes
    # from stage 2 below.
    #
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
    candidate_norms = [row["norm"] for row in cursor.fetchall()]
    if not candidate_norms:
        return []

    # Stage 2 — rerank: score every candidate against the full phrase.
    # token_sort_ratio (not WRatio — see module docstring "WHY token_sort_ratio")
    # measures whole-phrase similarity, so a query that names only a fragment
    # of a title scores low instead of the high partial-match score WRatio
    # would give it. process.extract returns (choice, score, index) tuples
    # already sorted by score descending.
    ranked = process.extract(
        q_norm, candidate_norms, scorer=fuzz.token_sort_ratio, limit=k
    )

    results: list[TitleMatch] = []
    for norm, score, _idx in ranked:
        if score <= 0.0:
            continue
        surface_rows = state.conn.execute(
            f"SELECT surface FROM {table} WHERE norm = ? ORDER BY surface", (norm,)
        ).fetchall()
        results.append(
            TitleMatch(
                normalized_title=norm,
                score=score / 100.0,
                surface_forms=[r["surface"] for r in surface_rows],
                entity_class=table,
            )
        )

    return results


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def rank_titles(phrase: str, k: int = 3, *, entity_class: str = "course") -> list[TitleMatch]:
    """Rank a KG title corpus (course or book) against ``phrase``.

    Opens a fresh, read-only connection to the committed ``entities.db`` for
    the duration of this call (see module docstring for why connections are
    not cached).

    Returns up to ``k`` results sorted by similarity (highest first). Returns
    ``[]`` if the phrase yields no usable stems, or if no candidate title
    shares a stemmed word with the phrase.

    Args:
        phrase: Raw content phrase from the user question (after entity and
                stopword tokens have been removed), e.g.
                "αρχιτεκτονικη υπολογιστων". Accents and casing are
                normalized internally.
        k: Maximum number of ranked candidates to return. Default 3.
        entity_class: Which corpus to search — ``"course"`` (default) or
                      ``"book"``. Keyword-only so a bare third positional
                      argument (an easy mix-up with ``k``) can't happen, and
                      defaulted so every existing call site is unaffected.

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
        entity_class: Which table to build/query — ``"course"`` (default) or
                      ``"book"``. Lets a test build a book fixture corpus and
                      assert the ranker treats it identically to a course one.

    Returns:
        List of ``TitleMatch`` objects sorted by score descending.

    Raises:
        ValueError: If ``entity_class`` is not a known title class.
    """
    state = _build_index(surface_map, entity_class)
    try:
        return _rank(phrase, k, state)
    finally:
        state.conn.close()
