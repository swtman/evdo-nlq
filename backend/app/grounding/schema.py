"""SQLite schema (DDL) for ``entities.db``, shared by the builder script and tests.

Defining the table layout in exactly one place means the committed database
(built by ``backend/scripts/build_entity_db.py``) and the throwaway in-memory
databases used by unit tests (``title_index.rank_titles_from_corpus``) can
never drift apart.

TABLES
------
``university`` / ``department`` — plain tables, looked up by exact
``normalize_greek()`` key (an ordinary B-tree index is enough; there are only
46 universities and 799 departments, so even a full scan would be instant).

One pair of tables per entry in ``TITLE_CLASSES`` (today: ``course`` and
``book``) — the base table holds one row per raw KG title string ("surface
form"); the matching ``<name>_fts`` is an FTS5 *external content* table that
indexes the ``norm`` column for full-text search without storing the text a
second time (see https://sqlite.org/fts5.html#external_content_tables).
Word-prefix search (``"αρχιτεκτ"*``) is what makes candidate lookup fast: it
narrows tens of thousands of titles down to a few hundred candidates *before*
the more expensive ``rapidfuzz`` reranking step runs (see ``title_index.py``).

WHY SEPARATE TABLES PER CLASS, NOT ONE GENERIC ``title(class, ...)`` TABLE?
----------------------------------------------------------------------------
The candidate-generation query is
``... WHERE <name>_fts MATCH ? ORDER BY bm25(<name>_fts) LIMIT 500`` — the
``ORDER BY bm25`` is load-bearing (see ``title_index.py`` for the bug it
fixes). If course and book titles shared one FTS index, that 500-candidate
budget would be split across the *combined* corpus instead of each class
getting its own clean budget, silently reintroducing the same class of
truncation bug in a subtler form (a book's true match could be crowded out
of the top 500 by unrelated courses sharing a stem, and vice versa).
Filtering ``WHERE class = 'book'`` after ``MATCH`` doesn't help — ``bm25``
has already ranked the merged set, so recovering a per-class budget would
mean two queries anyway, making the "one table" simplification illusory.

Separate explicit tables also match the existing pattern: ``university`` and
``department`` are already separate tables, not a polymorphic ``entity(type,
...)`` design. The DDL is still generated from one template (``_title_ddl``)
so adding a third title-bearing class is a one-word change to
``TITLE_CLASSES``, not a copy-pasted table definition.
"""

from __future__ import annotations

import sqlite3

# Every entity class that gets its own title-search table (base + FTS5 pair).
# The single source of truth for which classes exist — imported by
# title_index.py (to validate entity_class) and api/entities.py (to validate
# the ?class= query param) instead of each hardcoding its own set.
TITLE_CLASSES: tuple[str, ...] = ("course", "book")

_BASE_SQL = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL   -- e.g. meta['snapshot'] = '2026-07-30' (KG dump date)
);

CREATE TABLE IF NOT EXISTS university (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL,   -- canonical evdx:name label, exact KG string
    norm TEXT NOT NULL    -- normalize_greek(name), used for lookup
);
CREATE INDEX IF NOT EXISTS university_norm_idx ON university(norm);

CREATE TABLE IF NOT EXISTS department (
    id         INTEGER PRIMARY KEY,
    university TEXT NOT NULL,   -- parent university's canonical name
    department TEXT NOT NULL,   -- canonical department name (may include a
                                 -- "(ΚΑΤΑΡΓΗΘΗΚΕ)"-style status suffix)
    norm       TEXT NOT NULL    -- normalize_greek(department), status suffix stripped
);
CREATE INDEX IF NOT EXISTS department_norm_idx ON department(norm);
"""


def _title_ddl(name: str) -> str:
    """DDL for one title corpus: base table + norm index + FTS5 index.

    ``name`` becomes the table name and the FTS5 table name (``{name}_fts``).
    Only ever called with values from ``TITLE_CLASSES`` — never user input.
    """
    return f"""
CREATE TABLE IF NOT EXISTS {name} (
    id      INTEGER PRIMARY KEY,
    surface TEXT NOT NULL,   -- exact KG evdx:title literal (for SPARQL VALUES)
    norm    TEXT NOT NULL    -- normalize_greek(surface), what we search against
);
CREATE INDEX IF NOT EXISTS {name}_norm_idx ON {name}(norm);

-- External-content FTS5 table: 'content' points back at `{name}` so the title
-- text is stored once, not duplicated inside the FTS index.
CREATE VIRTUAL TABLE IF NOT EXISTS {name}_fts USING fts5(
    norm,
    content='{name}',
    content_rowid='id',
    tokenize='unicode61'
);
"""


# Data Definition Language for the whole database. Executed as one script via
# ``sqlite3.Connection.executescript`` so all statements share one transaction.
_SCHEMA_SQL = _BASE_SQL + "".join(_title_ddl(name) for name in TITLE_CLASSES)


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes on ``conn`` (idempotent — safe to call twice).

    Args:
        conn: An open SQLite connection, either to a real file or ``:memory:``.
    """
    conn.executescript(_SCHEMA_SQL)


def sync_title_fts(conn: sqlite3.Connection, table: str) -> None:
    """(Re)populate ``<table>_fts`` from the current contents of ``<table>``.

    Call this once after bulk-inserting rows into ``table``. Safe to call on
    an already-populated FTS table only if it is empty first — callers that
    rebuild from scratch (the builder script, ``rank_titles_from_corpus``'s
    in-memory fixture) always create a fresh table, so this is a plain insert.

    Args:
        conn: An open SQLite connection.
        table: One of ``TITLE_CLASSES`` (e.g. ``"course"`` or ``"book"``).
               Not validated here — callers are internal and always pass a
               constant; ``title_index.py`` validates values that trace back
               to external input (an HTTP query param) before they reach SQL.
    """
    conn.execute(f"INSERT INTO {table}_fts(rowid, norm) SELECT id, norm FROM {table}")
