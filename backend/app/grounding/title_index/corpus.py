"""SQLite access for the entity-title corpus (FTS5 and full-scan reads).

TWO SEPARATE CORPORA PER TITLE CLASS, NOT ONE MERGED ONE
-------------------------------------------------------------
Course and book titles live in separate tables (``course``/``course_fts`` and
``book``/``book_fts`` — see ``schema.py``), each with its own
``_CANDIDATE_LIMIT``-sized candidate budget (see the ``ORDER BY bm25`` comment
inside ``_fts_candidates``, which explains why that budget has to be ordered
at all). A merged FTS index would split that budget across both corpora and
reintroduce the same truncation bug in a subtler form — one that only bites
when both corpora are dense in the same stem.

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
classes, full-scan) query costs microseconds, so ``rank_titles`` (in
``search.py``) opens a fresh read-only connection per call and closes it
before returning. This also sidesteps the fact that a single
``sqlite3.Connection`` is not safe to share across FastAPI's threadpool
workers without extra locking.

For testing, ``_build_index`` builds a throwaway ``:memory:`` database from
an explicit corpus dict, bypassing ``entities.db`` entirely — used by
``search.rank_titles_from_corpus``.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from app.grounding.schema import FTS_CLASSES, TITLE_CLASSES, create_schema, sync_title_fts

# ---------------------------------------------------------------------------
# Internal index state
# ---------------------------------------------------------------------------


@dataclass
class _IndexState:
    """Wraps the SQLite connection and target table ``_rank`` queries against.

    A thin wrapper (rather than passing a bare connection around) so the
    ranking seam documented in the package docstring stays easy to swap
    again in the future. ``table`` is what makes this class-capable — the
    class currently being queried is exactly the kind of state this wrapper
    exists to carry.
    """

    conn: sqlite3.Connection
    table: str = "course"


# Maximum number of candidate titles the FTS5 stage hands to rapidfuzz, PER
# CLASS — course and book each get their own budget from their own separate
# FTS index (see "TWO SEPARATE CORPORA" above). Only applies to FTS-backed
# classes (course, book); university/department scan their full (46 / 379
# row) table instead — see ``policy._MatchPolicy.use_fts``.
_CANDIDATE_LIMIT = 500


# ---------------------------------------------------------------------------
# Index construction (test fixture only — never touches entities.db)
# ---------------------------------------------------------------------------


def _build_index(
    surface_map: dict[str, list[str]],
    entity_class: str = "course",
    *,
    parent_map: dict[str, list[str]] | None = None,
) -> _IndexState:
    """Build a throwaway in-memory SQLite database from ``surface_map``.

    Pure with respect to the filesystem — never touches ``entities.db``. Used
    by ``search.rank_titles_from_corpus`` (tests) so tests are fully isolated
    from the live data and from each other.

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
# Candidate generation (SQL read path)
# ---------------------------------------------------------------------------


def _fts_candidates(state: _IndexState, stems: list[str]) -> list[str]:
    """Stage 1 (FTS-backed classes only) — which titles share a stemmed word?

    High recall by design; precision comes from the rerank stage in
    ``search._rank``. Deliberately high-recall/low-precision: a title needs
    only ONE stemmed word in common with the query to become a candidate.

    Args:
        state: An ``_IndexState`` whose ``table`` is in ``schema.FTS_CLASSES``.
        stems: Non-empty stem list from ``search._fts_query_terms``.

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
    # `state.table` is checked against the closed TITLE_CLASSES tuple in
    # `search._rank` before this function is ever called, and this function
    # is only reached for classes in FTS_CLASSES.
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
    the package docstring). At 46 / 379 distinct names, a full scan is both
    fast and — unlike FTS prefix retrieval at this row count — lossless
    (ADR-020 M2 measured FTS candidate coverage as low as 89% recall here).

    Args:
        state: An ``_IndexState`` whose ``table`` is NOT in ``FTS_CLASSES``.

    Returns:
        Every distinct normalized name in the table.
    """
    cursor = state.conn.execute(f"SELECT DISTINCT norm FROM {state.table}")
    return [row["norm"] for row in cursor.fetchall()]


# ---------------------------------------------------------------------------
# Row hydration (SQL read path)
# ---------------------------------------------------------------------------


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
