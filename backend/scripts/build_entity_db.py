"""build_entity_db.py — build backend/app/data/entities.db from EvdoGraph labels.

WHAT THIS SCRIPT DOES
-----------------------
Produces the single SQLite database the grounding module reads at runtime
(``app/grounding/db.py``): university names, department names, course titles,
and book titles, each keyed by their ``normalize_greek()`` form for fast
lookup. Course and book additionally get an FTS5 full-text index for the
candidate-generation stage of ``app/grounding/title_index.py`` — university
and department deliberately do NOT (at 46 / 379 rows a full table scan beats
FTS on both speed and recall; see ADR-020) — (see ADR-018, ADR-019, ADR-020).

This replaces two things at once:
  1. The old ``scripts/dump_labels.py`` + ``scripts/grounding_labels.json``
     pair, which produced a gitignored 7.7 MB JSON file that ``gazetteer.py``
     read into memory on every process start (and which was never actually
     present in git or in the Docker image — see ADR-018 for the bug this
     caused).
  2. The runtime TF-IDF vectorizer fit that used to happen inside
     ``title_index.py`` on the first grounded query (a ~5-6 second one-time
     cost; ADR-015).

Universities, departments, courses, and books are all cleaned and
deduplicated here, offline, once — not on every server start.

WHERE THE RAW DATA COMES FROM
-------------------------------
Either:
  (a) live GraphDB, via the same SPARQL queries as the old ``dump_labels.py``
      plus a book-title query (default), or
  (b) an existing ``grounding_labels.json``-shaped dump, via
      ``--from-json <path>`` — useful for rebuilding without hitting the
      network, e.g. while iterating on the cleaning/schema logic. Older dumps
      (from before books were added) have no ``"books"`` key — read
      defensively, warn, and produce an empty (but valid) book corpus rather
      than failing.

CLEANING RULES (courses and books — universities/departments are already clean)
---------------------------------------------------------------------------------
Both title corpora go through the identical ``clean_titles()`` function in
``app/grounding/clean.py`` — see that module's docstring for the full
reasoning, in short:
  - The stored ``surface`` is the RAW KG literal, untouched. SPARQL matches
    literals by exact code-point equality, so any whitespace-collapsing
    applied before storage would silently break ``VALUES`` bindings for
    titles containing invisible characters like NBSP (found in 52 real book
    titles; the same bug almost certainly affects some course titles too —
    it was never separately measured before this fix).
  - A whitespace-collapsed form is used ONLY to validate non-emptiness and to
    compute ``norm`` (the search key) — ranking behavior is therefore
    unchanged by this fix.
  - Titles containing U+FFFD (mojibake) or a literal newline are dropped.
  - Surface forms are grouped by ``normalize_greek()`` key, so KG variants of
    the same title (ALL-CAPS accent-free vs. mixed-case accented) end up as
    multiple ``surface`` rows sharing one ``norm`` value.
  Every drop is counted and reported, itemized by reason — see "Report what
  was dropped" in CLAUDE.md's cost-awareness section; silent truncation is
  not acceptable for a data artifact this deliberately curated.

USAGE (from backend/)
-----------------------
    uv run python scripts/build_entity_db.py
    uv run python scripts/build_entity_db.py --endpoint http://lod.csd.auth.gr:7200/repositories/EvdoGraph
    uv run python scripts/build_entity_db.py --from-json ../scripts/grounding_labels.json
    uv run python scripts/build_entity_db.py --output app/data/entities.db --snapshot 2026-07-30
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

# Allow running from backend/ with: uv run python scripts/build_entity_db.py
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.grounding.clean import DropCounts, clean_titles  # noqa: E402
from app.grounding.normalize import normalize_greek  # noqa: E402
from app.grounding.schema import FTS_CLASSES, create_schema, sync_title_fts  # noqa: E402

try:
    from SPARQLWrapper import JSON, SPARQLWrapper
except ImportError:  # pragma: no cover - only hit without --from-json
    SPARQLWrapper = None  # type: ignore[assignment,misc]
    JSON = None  # type: ignore[assignment]

DEFAULT_ENDPOINT = "http://lod.csd.auth.gr:7200/repositories/EvdoGraph"
PREFIXES = "PREFIX evdx: <https://w3id.org/evdoxus#>\n"

UNI_QUERY = PREFIXES + """
SELECT DISTINCT ?uname WHERE {
  ?u a evdx:University ;
     evdx:name ?uname .
}
ORDER BY ?uname
"""

DEPT_QUERY = PREFIXES + """
SELECT DISTINCT ?uname ?dname WHERE {
  ?u a evdx:University ;
     evdx:name ?uname ;
     evdx:hasDepartment ?d .
  ?d evdx:name ?dname .
}
ORDER BY ?uname ?dname
"""

COURSE_QUERY = PREFIXES + """
SELECT DISTINCT ?ctitle WHERE {
  ?c a evdx:Course ;
     evdx:title ?ctitle .
}
ORDER BY ?ctitle
"""

BOOK_QUERY = PREFIXES + """
SELECT DISTINCT ?btitle WHERE {
  ?b a evdx:Book ;
     evdx:title ?btitle .
}
ORDER BY ?btitle
"""


# ---------------------------------------------------------------------------
# Raw data acquisition
# ---------------------------------------------------------------------------


def fetch_from_graphdb(endpoint: str, timeout: int = 600) -> dict[str, Any]:
    """Run the four label queries against a live GraphDB endpoint.

    Mirrors the queries in the old ``scripts/dump_labels.py`` for
    universities/departments/courses, plus a book-title query added for
    ADR-019, so the resulting raw shape is a superset of a
    ``grounding_labels.json`` dump.
    """
    if SPARQLWrapper is None:
        print("Install SPARQLWrapper first: uv add sparqlwrapper", file=sys.stderr)
        sys.exit(2)

    def run(query: str) -> list[dict]:
        sparql = SPARQLWrapper(endpoint)
        sparql.setTimeout(timeout)
        sparql.setQuery(query)
        sparql.setReturnFormat(JSON)
        result = sparql.queryAndConvert()  # type: ignore[assignment]
        return result["results"]["bindings"]

    print(f"Querying universities from {endpoint} ...")
    universities = [b["uname"]["value"] for b in run(UNI_QUERY)]

    print("Querying departments ...")
    departments = [
        {"university": b["uname"]["value"], "department": b["dname"]["value"]}
        for b in run(DEPT_QUERY)
    ]

    print("Querying course titles ...")
    courses = [b["ctitle"]["value"] for b in run(COURSE_QUERY)]

    print("Querying book titles ...")
    books = [b["btitle"]["value"] for b in run(BOOK_QUERY)]

    return {
        "universities": universities,
        "departments": departments,
        "courses": courses,
        "books": books,
    }


def load_from_json(path: Path) -> dict[str, Any]:
    """Load a ``grounding_labels.json``-shaped dump from disk (no network).

    Older dumps (from before book titles were added) have no ``"books"``
    key — that is handled by the caller reading with ``raw.get("books", [])``
    and warning, not here, so this function's contract stays "just read the
    file" regardless of which keys it happens to contain.
    """
    print(f"Loading raw labels from {path} ...")
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Cleaning
# ---------------------------------------------------------------------------


def clean_universities(raw_universities: list[str]) -> list[str]:
    """Dedup to distinct canonical labels, sorted (mirrors old gazetteer._load)."""
    return sorted(set(raw_universities))


def clean_departments(raw_departments: list[dict[str, str]]) -> list[dict[str, str]]:
    """Dedup (university, department) pairs, sorted (mirrors old gazetteer._load)."""
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, str]] = []
    for entry in raw_departments:
        pair = (entry["university"], entry["department"])
        if pair not in seen:
            seen.add(pair)
            result.append({"university": entry["university"], "department": entry["department"]})
    result.sort(key=lambda d: (d["university"], d["department"]))
    return result


# ---------------------------------------------------------------------------
# Database writing
# ---------------------------------------------------------------------------


def _insert_rows(
    conn: sqlite3.Connection, table: str, rows: list[tuple[str, str, str | None]]
) -> None:
    """Insert ``(norm, surface, parent)`` rows into ``table``.

    Syncs the table's FTS5 index afterwards — but only for classes that have
    one (``schema.FTS_CLASSES`` — course, book). university/department have
    no FTS table to sync (ADR-020; see ``schema.py``'s module docstring "FTS5
    — SELECTIVELY, NOT UNIFORMLY").
    """
    conn.executemany(f"INSERT INTO {table}(norm, surface, parent) VALUES (?, ?, ?)", rows)
    if table in FTS_CLASSES:
        sync_title_fts(conn, table)


def _insert_title_rows(conn: sqlite3.Connection, table: str, surface_map: dict[str, set[str]]) -> None:
    """Insert ``(norm, surface, NULL)`` rows for one title corpus (course/book)."""
    rows = [
        (norm, surface, None)
        for norm, surfaces in surface_map.items()
        for surface in sorted(surfaces)
    ]
    _insert_rows(conn, table, rows)


def build_database(
    universities: list[str],
    departments: list[dict[str, str]],
    course_map: dict[str, set[str]],
    book_map: dict[str, set[str]],
    output: Path,
    snapshot: str,
) -> None:
    """Write all cleaned data into a fresh SQLite database at ``output``."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()  # start from a clean file — avoids stale leftover rows

    conn = sqlite3.connect(str(output))
    try:
        create_schema(conn)

        conn.execute("INSERT INTO meta(key, value) VALUES ('snapshot', ?)", (snapshot,))

        # University: no parent (it IS the top of the hierarchy).
        uni_rows = [(normalize_greek(name), name, None) for name in universities]
        _insert_rows(conn, "university", uni_rows)

        # Department: parent is the owning university's canonical name. A
        # department name shared by several universities becomes several
        # rows under the same `norm` — see title_index.TitleMatch.parents.
        dept_rows = [
            (normalize_greek(d["department"]), d["department"], d["university"])
            for d in departments
        ]
        _insert_rows(conn, "department", dept_rows)

        _insert_title_rows(conn, "course", course_map)
        _insert_title_rows(conn, "book", book_map)

        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument(
        "--from-json",
        type=Path,
        default=None,
        help="Skip GraphDB and build from an existing grounding_labels.json-shaped dump",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent.parent / "app" / "data" / "entities.db",
        help="Where to write the database (default: backend/app/data/entities.db)",
    )
    parser.add_argument(
        "--snapshot",
        default="unknown",
        help="Label recorded in the meta table for when this dump was taken, e.g. 2026-07-30",
    )
    args = parser.parse_args()

    raw = load_from_json(args.from_json) if args.from_json else fetch_from_graphdb(args.endpoint)

    universities = clean_universities(raw["universities"])
    departments = clean_departments(raw["departments"])

    raw_books = raw.get("books", [])
    if not raw_books and args.from_json:
        print(
            "WARNING: dump has no 'books' key (or it's empty) — book search "
            "will find nothing until you rebuild from a newer dump or live GraphDB.",
            file=sys.stderr,
        )

    course_map, course_drops = clean_titles(raw.get("courses", []))
    book_map, book_drops = clean_titles(raw_books)

    build_database(universities, departments, course_map, book_map, args.output, args.snapshot)

    def _report(label: str, raw_count: int, surface_map: dict[str, set[str]], drops: DropCounts) -> None:
        unique_surfaces = sum(len(s) for s in surface_map.values())
        print(f"{label} titles (raw):   {raw_count}")
        print(f"  dropped — mojibake:   {drops.mojibake}")
        print(f"  dropped — empty:      {drops.empty}")
        print(f"  dropped — newline:    {drops.newline}")
        print(f"  unique surface forms: {unique_surfaces}")
        print(f"  unique normalized:    {len(surface_map)}")

    print()
    print(f"Universities:          {len(universities)}")
    print(f"Departments:           {len(departments)}")
    _report("Course", len(raw.get("courses", [])), course_map, course_drops)
    print()
    _report("Book", len(raw_books), book_map, book_drops)
    print(f"\nSnapshot: {args.snapshot}")
    print(f"Wrote -> {args.output}")


if __name__ == "__main__":
    main()
