"""SQLite schema (DDL) for `entities.db`, shared by the builder script and tests.

Defining the table layout in exactly one place means the committed database
(built by `backend/scripts/build_entity_db.py`) and the throwaway in-memory
databases used by unit tests (`title_index.rank_titles_from_corpus`) can
never drift apart.

TABLES
------
One table per entry in `TITLE_CLASSES` — today: `course`, `book`,
`university`, `department`. "Title" here means the searchable display
label: 
`evdx:title` for course/book, 
`evdx:name` for university/department
Unified them onto the same
`surface`/`norm`/`parent` shape so all four classes go through one
ranking function, `title_index.rank_titles`).

`parent` is `NULL` for every class except `department`, where it holds
the parent university's canonical name — the one piece of data that doesn't
fit the plain `surface`/`norm` shape (a department can be shared by
several universities, so this is one parent per *row*, not per normalized
title; see `title_index.TitleMatch.parents`).

FTS5 — SELECTIVELY, NOT UNIFORMLY
-----------------------------------
`course` and `book` also get a `<name>_fts` FTS5 external content
table indexing the `norm` column, used for full-text candidate generation
before the rapidfuzz reranking step (see `title_index.py`). Word-prefix
search (`"αρχιτεκτ"*`) narrows tens of thousands of titles down to a few
hundred candidates before the more expensive fuzzy-scoring step runs.

`university` and `department` deliberately get NO FTS table.  There are
only 46 / 379 distinct names — small enough that a full table scan is both
cheap and, measured empirically (ADR-020), *more accurate* than FTS prefix
retrieval would be: worst-case candidate coverage from stem-prefix matching
was 89% recall for a department name, vs. 100% for a full scan.  Building an
FTS index nobody benefits from is worse than not building it — it's a trap
for the next reader who assumes every class in `TITLE_CLASSES` is FTS-
backed.  See `title_index._POLICY` for how each class is actually matched.

WHY SEPARATE TABLES PER CLASS, NOT ONE GENERIC `title(class, ...)` TABLE?
----------------------------------------------------------------------------
The candidate-generation query is
`... WHERE <name>_fts MATCH ? ORDER BY bm25(<name>_fts) LIMIT 500` — the
`ORDER BY bm25` is load-bearing (see `title_index.py` for the bug it
fixes). If course and book titles shared one FTS index, that 500-candidate
budget would be split across the *combined* corpus instead of each class
getting its own clean budget, silently reintroducing the same class of
truncation bug in a subtler form (a book's true match could be crowded out
of the top 500 by unrelated courses sharing a stem, and vice versa).
Filtering `WHERE class = 'book'` after `MATCH` doesn't help — `bm25`
has already ranked the merged set, so recovering a per-class budget would
mean two queries anyway, making the "one table" simplification illusory.

The DDL is still generated from one template (`_title_ddl`) so adding a
fifth class is a one-word change to `TITLE_CLASSES` (plus, if it's large
enough to need FTS, adding it to `_FTS_CLASSES`), not a copy-pasted table
definition.
"""

from __future__ import annotations

import sqlite3

# Every entity class searchable via title_index.rank_titles() — one base
# table each. The single source of truth for which classes exist — imported
# by title_index.py (to validate entity_class) and api/entities.py (to
# validate the ?class= query param) instead of each hardcoding its own set.
TITLE_CLASSES: tuple[str, ...] = ("course", "book", "university", "department")

# Classes small enough to enumerate exhaustively via GET /entities/list —
# ranked search over 46 / 379 rows is the wrong tool for "show me
# everything"; see api/entities.py and title_index.list_titles().
LISTABLE_CLASSES: tuple[str, ...] = ("university", "department")

# Classes that get an FTS5 candidate-generation index — see the module
# docstring "FTS5 — SELECTIVELY, NOT UNIFORMLY" for why university/department
# are deliberately excluded. Public (not `_FTS_CLASSES`) because
# title_index.py's per-class `_MatchPolicy` table derives its `use_fts`
# field from this same constant — one source of truth for "which classes are
# FTS-backed" shared by the DDL generator and the ranker.
FTS_CLASSES: frozenset[str] = frozenset({"course", "book"})

_BASE_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL   -- e.g. meta['snapshot'] = '2026-07-30' (KG dump date)
);
"""


def _title_ddl(name: str, *, fts: bool) -> str:
    """DDL for one entity corpus: base table + norm index, optionally + FTS5 index.

    Args:
        name: Becomes the table name and (if `fts`) the FTS5 table name
              (`{name}_fts`). Only ever called with values from
              `TITLE_CLASSES` — never user input.
        fts: Whether to also emit the FTS5 candidate-generation table.
             `True` for `course`/`book`, `False` for
             `university`/`department` — see module docstring.
    """
    base = f"""
CREATE TABLE IF NOT EXISTS {name} (
    id      INTEGER PRIMARY KEY,
    surface TEXT NOT NULL,   -- exact KG literal (evdx:title or evdx:name), for SPARQL VALUES
    norm    TEXT NOT NULL,   -- normalize_greek(surface), what we search against
    parent  TEXT              -- NULL except department: parent university's canonical name
);
CREATE INDEX IF NOT EXISTS {name}_norm_idx ON {name}(norm);
"""
    if not fts:
        return base

    # External-content FTS5 table: 'content' points back at `{name}` so the
    # title text is stored once, not duplicated inside the FTS index.
    return (
        base
        + f"""
CREATE VIRTUAL TABLE IF NOT EXISTS {name}_fts USING fts5(
    norm,
    content='{name}',
    content_rowid='id',
    tokenize='unicode61'
);
"""
    )


# Data Definition Language for the whole database. Executed as one script via
# `sqlite3.Connection.executescript` so all statements share one transaction.
_SCHEMA_SQL = _BASE_SQL + "".join(
    _title_ddl(name, fts=name in FTS_CLASSES) for name in TITLE_CLASSES
)


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes on `conn` (idempotent — safe to call twice).

    Args:
        conn: An open SQLite connection, either to a real file or `:memory:`.
    """
    conn.executescript(_SCHEMA_SQL)


def sync_title_fts(conn: sqlite3.Connection, table: str) -> None:
    """(Re)populate `<table>_fts` from the current contents of `<table>`.

    Call this once after bulk-inserting rows into `table`. Safe to call on
    an already-populated FTS table only if it is empty first — callers that
    rebuild from scratch (the builder script, `rank_titles_from_corpus`'s
    in-memory fixture) always create a fresh table, so this is a plain insert.

    Args:
        conn: An open SQLite connection.
        table: One of `FTS_CLASSES` (`"course"` or `"book"`) — the only
               classes that have an `<table>_fts` table to populate.

    Raises:
        ValueError: If `table` is not an FTS-backed class (`university`
                    and `department` have no FTS table — see module
                    docstring "FTS5 — SELECTIVELY, NOT UNIFORMLY").
    """
    if table not in FTS_CLASSES:
        raise ValueError(
            f"{table!r} has no FTS table to sync; only {sorted(FTS_CLASSES)} do"
        )
    conn.execute(f"INSERT INTO {table}_fts(rowid, norm) SELECT id, norm FROM {table}")
