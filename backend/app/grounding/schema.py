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

``course`` / ``course_fts`` — ``course`` holds one row per raw KG title
string ("surface form"); ``course_fts`` is an FTS5 *external content* table
that indexes the ``norm`` column for full-text search without storing the
text a second time (see https://sqlite.org/fts5.html#external_content_tables).
Word-prefix search (``"αρχιτεκτ"*``) is what makes candidate lookup fast: it
narrows ~73,000 titles down to a few hundred candidates *before* the more
expensive ``rapidfuzz`` reranking step runs (see ``title_index.py``).
"""

from __future__ import annotations

import sqlite3

# Data Definition Language for the whole database. Executed as one script via
# ``sqlite3.Connection.executescript`` so all statements share one transaction.
_SCHEMA_SQL = """
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

CREATE TABLE IF NOT EXISTS course (
    id      INTEGER PRIMARY KEY,
    surface TEXT NOT NULL,   -- exact KG evdx:title literal (for SPARQL VALUES)
    norm    TEXT NOT NULL    -- normalize_greek(surface), what we search against
);
CREATE INDEX IF NOT EXISTS course_norm_idx ON course(norm);

-- External-content FTS5 table: 'content' points back at `course` so the title
-- text is stored once (in `course`), not duplicated inside the FTS index.
CREATE VIRTUAL TABLE IF NOT EXISTS course_fts USING fts5(
    norm,
    content='course',
    content_rowid='id',
    tokenize='unicode61'
);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    """Create all tables and indexes on ``conn`` (idempotent — safe to call twice).

    Args:
        conn: An open SQLite connection, either to a real file or ``:memory:``.
    """
    conn.executescript(_SCHEMA_SQL)


def sync_course_fts(conn: sqlite3.Connection) -> None:
    """(Re)populate ``course_fts`` from the current contents of ``course``.

    Call this once after bulk-inserting rows into ``course``. Safe to call on
    an already-populated FTS table only if it is empty first — callers that
    rebuild from scratch (the builder script, ``rank_titles_from_corpus``'s
    in-memory fixture) always create a fresh table, so this is a plain insert.
    """
    conn.execute("INSERT INTO course_fts(rowid, norm) SELECT id, norm FROM course")
