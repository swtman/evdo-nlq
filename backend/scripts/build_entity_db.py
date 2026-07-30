"""build_entity_db.py — build backend/app/data/entities.db from EvdoGraph labels.

WHAT THIS SCRIPT DOES
-----------------------
Produces the single SQLite database the grounding module reads at runtime
(``app/grounding/db.py``): university names, department names, and course
titles, each keyed by their ``normalize_greek()`` form for fast lookup, plus
an FTS5 full-text index over course titles for the candidate-generation stage
of ``app/grounding/title_index.py`` (see ADR-018).

This replaces two things at once:
  1. The old ``scripts/dump_labels.py`` + ``scripts/grounding_labels.json``
     pair, which produced a gitignored 7.7 MB JSON file that ``gazetteer.py``
     read into memory on every process start (and which was never actually
     present in git or in the Docker image — see ADR-018 for the bug this
     caused).
  2. The runtime TF-IDF vectorizer fit that used to happen inside
     ``title_index.py`` on the first grounded query (a ~5-6 second one-time
     cost; ADR-015).

Both universities/departments and courses are cleaned and deduplicated here,
offline, once — not on every server start.

WHERE THE RAW DATA COMES FROM
-------------------------------
Either:
  (a) live GraphDB, via the same three SPARQL queries as the old
      ``dump_labels.py`` (default), or
  (b) an existing ``scripts/grounding_labels.json``-shaped dump, via
      ``--from-json <path>`` — useful for rebuilding without hitting the
      network, e.g. while iterating on the cleaning/schema logic.

CLEANING RULES (course titles only — universities/departments are already clean)
------------------------------------------------------------------------------
  - Collapse internal whitespace and strip leading/trailing whitespace
    (the raw KG dump has titles like "\\tΑΝΕΞΑΡΤΗΤΗ ΣΠΟΥΔΗ 2").
  - Drop titles that become empty after that.
  - Drop titles containing U+FFFD (the Unicode "replacement character" —
    evidence of a mojibake/encoding-corrupted record).
  - Group surface forms by their ``normalize_greek()`` key so that KG
    variants of the same title (ALL-CAPS accent-free vs. mixed-case accented)
    end up as multiple ``surface`` rows sharing one ``norm`` value.
  Every drop is counted and reported — see "Report what was dropped" in
  CLAUDE.md's cost-awareness section; silent truncation is not acceptable
  for a data artifact this deliberately curated.

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

from app.grounding.normalize import normalize_greek  # noqa: E402
from app.grounding.schema import create_schema, sync_course_fts  # noqa: E402

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


# ---------------------------------------------------------------------------
# Raw data acquisition
# ---------------------------------------------------------------------------


def fetch_from_graphdb(endpoint: str, timeout: int = 600) -> dict[str, Any]:
    """Run the three label queries against a live GraphDB endpoint.

    Mirrors the queries in the old ``scripts/dump_labels.py`` exactly, so the
    resulting raw shape is identical to a ``grounding_labels.json`` dump.
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

    return {"universities": universities, "departments": departments, "courses": courses}


def load_from_json(path: Path) -> dict[str, Any]:
    """Load a ``grounding_labels.json``-shaped dump from disk (no network)."""
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


def clean_courses(raw_courses: list[str]) -> tuple[dict[str, set[str]], int]:
    """Clean and group raw course titles by their normalized key.

    Returns:
        A tuple of:
          - ``surface_map``: ``normalize_greek(title) -> {raw surface form, ...}``.
          - ``dropped``: count of raw titles discarded (empty after whitespace
            collapse, or containing a Unicode replacement character).
    """
    surface_map: dict[str, set[str]] = {}
    dropped = 0
    for raw_title in raw_courses:
        surface = " ".join(raw_title.split())  # collapse/trim whitespace
        if not surface or "�" in surface:
            dropped += 1
            continue
        norm = normalize_greek(surface)
        if not norm:
            dropped += 1
            continue
        surface_map.setdefault(norm, set()).add(surface)
    return surface_map, dropped


# ---------------------------------------------------------------------------
# Database writing
# ---------------------------------------------------------------------------


def build_database(
    universities: list[str],
    departments: list[dict[str, str]],
    surface_map: dict[str, set[str]],
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

        conn.executemany(
            "INSERT INTO university(name, norm) VALUES (?, ?)",
            [(name, normalize_greek(name)) for name in universities],
        )

        conn.executemany(
            "INSERT INTO department(university, department, norm) VALUES (?, ?, ?)",
            [
                (d["university"], d["department"], normalize_greek(d["department"]))
                for d in departments
            ],
        )

        course_rows = [
            (norm, surface)
            for norm, surfaces in surface_map.items()
            for surface in sorted(surfaces)
        ]
        conn.executemany("INSERT INTO course(norm, surface) VALUES (?, ?)", course_rows)
        sync_course_fts(conn)

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
    surface_map, dropped = clean_courses(raw.get("courses", []))

    raw_course_count = len(raw.get("courses", []))
    unique_surfaces = sum(len(s) for s in surface_map.values())

    build_database(universities, departments, surface_map, args.output, args.snapshot)

    print()
    print(f"Universities:          {len(universities)}")
    print(f"Departments:           {len(departments)}")
    print(f"Course titles (raw):   {raw_course_count}")
    print(f"  dropped (bad data):  {dropped}")
    print(f"  unique surface forms:{unique_surfaces}")
    print(f"  unique normalized:   {len(surface_map)}")
    print(f"Wrote -> {args.output}")


if __name__ == "__main__":
    main()
