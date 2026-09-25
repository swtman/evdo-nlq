"""SQLite schema (DDL) for `entities.db`, shared by the builder script and tests.

Defining the table layout in exactly one place means the committed database
(built by `backend/scripts/build_entity_db.py`) and the throwaway in-memory
databases used by unit tests (`title_index.search.rank_titles_from_corpus`)
can never drift apart.

TABLES
------
One table per entry in `TITLE_CLASSES` — today: `course`, `book`,
`university`, `department`. "Title" here means the searchable display
label: 
`evdx:title` for course/book, 
`evdx:name` for university/department
Unified them onto the same
`surface`/`norm`/`parent` shape so all four classes go through one
ranking function, `title_index.search.rank_titles`).

`parent` is `NULL` for every class except `department`, where it holds
the parent university's canonical name — the one piece of data that doesn't
fit the plain `surface`/`norm` shape (a department can be shared by
several universities, so this is one parent per *row*, not per normalized
title; see `title_index.policy.TitleMatch.parents`).

FTS5 — SELECTIVELY, NOT UNIFORMLY
-----------------------------------
`course` and `book` also get a `<name>_fts` FTS5 external content
table indexing the `norm` column, used for full-text candidate generation
before the rapidfuzz reranking step (see `title_index/corpus.py`). Word-prefix
search (`"αρχιτεκτ"*`) narrows tens of thousands of titles down to a few
hundred candidates before the more expensive fuzzy-scoring step runs.

`university` and `department` deliberately get NO FTS table.  There are
only 46 / 379 distinct names — small enough that a full table scan is both
cheap and, measured empirically (ADR-020), *more accurate* than FTS prefix
retrieval would be: worst-case candidate coverage from stem-prefix matching
was 89% recall for a department name, vs. 100% for a full scan.  Building an
FTS index nobody benefits from is worse than not building it — it's a trap
for the next reader who assumes every class in `TITLE_CLASSES` is FTS-
backed.  See `title_index/policy.py`'s `_POLICY` for how each class is
actually matched.

WHY SEPARATE TABLES PER CLASS, NOT ONE GENERIC `title(class, ...)` TABLE?
----------------------------------------------------------------------------
The candidate-generation query is
`... WHERE <name>_fts MATCH ? ORDER BY bm25(<name>_fts) LIMIT 500` — the
`ORDER BY bm25` is load-bearing (see `title_index/corpus.py` for the bug it
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

# Every entity class searchable via title_index.search.rank_titles() — one
# base table each. The single source of truth for which classes exist —
# imported by title_index/ (to validate entity_class) and api/entities.py
# (to validate the ?class= query param) instead of each hardcoding its own set.
TITLE_CLASSES: tuple[str, ...] = ("course", "book", "university", "department")

# Classes small enough to enumerate exhaustively via GET /entities/list —
# ranked search over 46 / 379 rows is the wrong tool for "show me
# everything"; see api/entities.py and title_index.search.list_titles().
LISTABLE_CLASSES: tuple[str, ...] = ("university", "department")

# Classes that get an FTS5 candidate-generation index — see the module
# docstring "FTS5 — SELECTIVELY, NOT UNIFORMLY" for why university/department
# are deliberately excluded. Public (not `_FTS_CLASSES`) because
# title_index/policy.py's per-class `_MatchPolicy` table derives its `use_fts`
# field from this same constant — one source of truth for "which classes are
# FTS-backed" shared by the DDL generator and the ranker.
FTS_CLASSES: frozenset[str] = frozenset({"course", "book"})

# Classes with a WORD index for the ΟΝΤΟΛΟΓΙΑ page search (ADR-030;
# title_index/word_search.py) — a different job from the `rank_titles` ranking above:
# a person looking a name up, matched word by word, "(…)" included. Per class:
#   {class}_name      one row per EXACT name: norm (group key), surface (raw literal),
#                     words (normalize.search_fold of the surface, space-joined);
#   {class}_name_fts  FTS5 over `words` (candidate retrieval);
#   {class}_vocab     each distinct word, flagged when it is a connector (lexicon
#                     _SEARCH_CONNECTORS — matched only as a whole word).
# This does not contradict "university/department get NO FTS table" above: that is
# about `rank_titles`' candidate generation, which stays a full scan.
SEARCH_CLASSES: tuple[str, ...] = ("university", "department")

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
    norm    TEXT NOT NULL,   -- search key: normalize.title_key(surface) for course/book,
                             -- normalize_greek(surface) for university/department
    family  TEXT,            -- course/book: normalize.title_family(surface) — the key
                             -- without a trailing "(…)"/"[…]" (ADR-024) — stored ONLY
                             -- when it differs from norm (see family_column); else NULL
    parent  TEXT              -- NULL except department: parent university's canonical name
);
CREATE INDEX IF NOT EXISTS {name}_norm_idx ON {name}(norm);
CREATE INDEX IF NOT EXISTS {name}_family_idx ON {name}(family);
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


def _search_ddl(name: str) -> str:
    """DDL for one class's ΟΝΤΟΛΟΓΙΑ word index (see ``SEARCH_CLASSES``).

    Args:
        name: One of ``SEARCH_CLASSES`` — never user input.
    """
    return f"""
CREATE TABLE IF NOT EXISTS {name}_name (
    id      INTEGER PRIMARY KEY,
    norm    TEXT NOT NULL,   -- group key, same as {name}.norm (normalize_greek)
    surface TEXT NOT NULL,   -- the exact KG literal, untouched
    words   TEXT NOT NULL    -- normalize.search_words(surface), space-joined
);
CREATE INDEX IF NOT EXISTS {name}_name_norm_idx ON {name}_name(norm);
CREATE VIRTUAL TABLE IF NOT EXISTS {name}_name_fts USING fts5(
    words,
    content='{name}_name',
    content_rowid='id',
    tokenize='unicode61'
);
CREATE TABLE IF NOT EXISTS {name}_vocab (
    word         TEXT PRIMARY KEY,
    is_connector INTEGER NOT NULL   -- 1: lexicon._SEARCH_CONNECTORS, whole-word match only
) WITHOUT ROWID;
"""


# Data Definition Language for the whole database. Executed as one script via
# `sqlite3.Connection.executescript` so all statements share one transaction.
_SCHEMA_SQL = (
    _BASE_SQL
    + "".join(_title_ddl(name, fts=name in FTS_CLASSES) for name in TITLE_CLASSES)
    + "".join(_search_ddl(name) for name in SEARCH_CLASSES)
)


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes on `conn` (idempotent — safe to call twice).

    Args:
        conn: An open SQLite connection, either to a real file or `:memory:`.
    """
    conn.executescript(_SCHEMA_SQL)


def family_column(norm: str, family: str) -> str | None:
    """Value to store in the ``family`` column for one course/book row (ADR-024).

    NULL unless the family key differs from the row's own ``norm`` — i.e. only
    for titles that actually have a trailing "(…)"/"[…]" tail (~13% of course
    surfaces). Storing it for every row duplicated ``norm`` and grew the
    committed database by ~58%; lookups use ``norm = ? OR family = ?``, which a
    NULL never matches, so behaviour is identical. Shared by the builder script
    and the in-memory test fixture so the two can never disagree.
    """
    return family if family and family != norm else None


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


def sync_search_index(conn: sqlite3.Connection, table: str) -> None:
    """(Re)build ``<table>_name``, its FTS5 index and ``<table>_vocab`` from ``<table>``.

    Call once after the base table is filled (builder script; in-memory test fixtures).
    Idempotent: the three derived tables are emptied first.

    Args:
        conn: An open SQLite connection whose schema came from ``create_schema``.
        table: One of ``SEARCH_CLASSES``.

    Raises:
        ValueError: If ``table`` has no word index.
    """
    # Imported here: normalize imports lexicon only, but keeping schema.py's top-level
    # imports to the standard library preserves its role as the dependency-free DDL module.
    from app.grounding.lexicon import _SEARCH_CONNECTORS
    from app.grounding.normalize import search_words

    if table not in SEARCH_CLASSES:
        raise ValueError(f"{table!r} has no word index; only {list(SEARCH_CLASSES)} do")

    conn.execute(f"DELETE FROM {table}_name")
    conn.execute(f"INSERT INTO {table}_name_fts({table}_name_fts) VALUES ('delete-all')")
    conn.execute(f"DELETE FROM {table}_vocab")

    names = conn.execute(
        f"SELECT DISTINCT norm, surface FROM {table} ORDER BY norm, surface"
    ).fetchall()
    rows = [(norm, surface, " ".join(search_words(surface))) for norm, surface in names]
    conn.executemany(f"INSERT INTO {table}_name(norm, surface, words) VALUES (?, ?, ?)", rows)
    conn.execute(f"INSERT INTO {table}_name_fts(rowid, words) SELECT id, words FROM {table}_name")

    vocab = sorted({w for _, _, words in rows for w in words.split()})
    conn.executemany(
        f"INSERT INTO {table}_vocab(word, is_connector) VALUES (?, ?)",
        [(w, int(w in _SEARCH_CONNECTORS)) for w in vocab],
    )
