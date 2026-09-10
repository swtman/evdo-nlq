"""Shared SQLite connection helper for the grounding module's entity database.

WHAT IS entities.db?
---------------------
A single SQLite file (`backend/app/data/entities.db`) holding four tables —
`university`, `department`, `course`, `book` — plus an FTS5 (full-text search)
index over course and book titles.

WHY COMMIT THE .db FILE TO GIT?
---------------------------------
`backend/app/` is already copied wholesale into the Docker image
(`backend/Dockerfile`). Putting the database inside it means the grounding
module works out of the box in Docker, in CI, and on a fresh clone.

USAGE
-----
Both `gazetteer.py` (universities/departments) and `title_index/search.py`
(courses) open their own connections via `get_connection()`. Each call opens
a fresh, read-only connection — this is deliberate: a single `sqlite3.Connection`
object is not safe to share across FastAPI's threadpool workers, and opening a
new one is cheap enough (microseconds) that there is no benefit to pooling it.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

# Path to the committed database: backend/app/grounding/db.py -> backend/app/
# (2 .parent calls) -> data/entities.db.
DB_PATH: Path = Path(__file__).parent.parent / "data" / "entities.db"


def get_connection() -> sqlite3.Connection:
    """Open a fresh, read-only connection to `entities.db`.

    Returns
    -------
    sqlite3.Connection
        A connection with `row_factory` set to `sqlite3.Row` so query
        results can be accessed by column name (`row["norm"]`) as well as
        by position. Callers are responsible for closing the connection
        (e.g. via `with get_connection() as conn:` or a `try/finally`).

    Raises
    ------
    FileNotFoundError
        If `entities.db` is missing. The file is checked into git and
        should always be present; if it isn't, run
        `uv run python scripts/build_entity_db.py` from `backend/` to
        regenerate it.
    """
    if not DB_PATH.exists():
        raise FileNotFoundError(
            f"Entity database not found: {DB_PATH}\n"
            "Run `uv run python scripts/build_entity_db.py` from backend/ "
            "to build it (see backend/scripts/build_entity_db.py)."
        )

    # mode=ro opens the file read-only; uri=True is required to pass a
    # "file:...?mode=ro" connection string instead of a plain path.
    uri = f"file:{DB_PATH.as_posix()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn
