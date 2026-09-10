"""Entity label store for the grounding module.

WHAT IS THE GAZETTEER?
----------------------
A gazetteer is a geographical/entity reference dictionary.  Here it holds the
canonical university and department names as they appear in the EvdoGraph KG
(field `evdx:name` values), plus a hand-curated map of common Greek university
abbreviations to their full canonical forms.

WHY A GAZETTEER?
----------------
The EvdoGraph KG stores University and department names in ALL-CAPS, accent-free Greek strings, e.g.
"ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ".  Users typically type abbreviated or
accented variants ("ΑΠΘ", "Αριστοτέλειο").  The gazetteer gives the linker
(linker.py) the canonical forms it needs to resolve user mentions to exact KG
labels — which then get injected into the SPARQL query.

DATA SOURCE
-----------
Labels are loaded from `backend/app/data/entities.db` (see `db.py`), a
SQLite database built offline by `backend/scripts/build_entity_db.py` from a
live EvdoGraph SPARQL snapshot. Deduplication already happened when the
database was built, so the rows read here are already distinct —
this module still dedups defensively on load in case the database is ever
rebuilt without going through the builder script.

MODULE-LEVEL CACHE
------------------
All public functions delegate to `_load()`, which populates `_cache` on the
first call and returns the cached dict on every subsequent call.  This mirrors
the pattern in `app/ontology/loader.py`: one file read per process lifetime.

NORMALIZED LOOKUP INDEX
-----------------------
`get_university_index()` and `get_department_index()` return dicts keyed on
`normalize_greek(label)` so that linker.py can perform accent/case-insensitive
lookups without re-normalizing on every query.  Department labels include
parenthetical status suffixes in the raw data (e.g. "(ΚΑΤΑΡΓΗΘΗΚΕ)"); the index
key is built after `normalize_greek` has stripped those suffixes, so abolished
departments are still reachable.

NORMALIZED LABEL LISTS (for fuzzy matching)
---------------------------------------------
`get_normalized_universities()` / `get_normalized_departments()` return
`(normalized_label, canonical_label[, parent_university])` tuples, precomputed
once here rather than by every caller.  This exists specifically for
`linker._stage3_fuzzy`, which runs `rapidfuzz.process.extractOne` against
these lists on every call to `resolve_mention` — and `hints.py` calls
`resolve_mention` roughly 20 times per question (every 1/2/3-token sliding
window, plus once more per token in `_tokens_used_by_entity`).  Before this
cache existed, `_stage3_fuzzy` re-ran `normalize_greek` over all 46 + 379
labels on every one of those calls — ~17,000 redundant normalizations per
question.
"""

from __future__ import annotations

from typing import TypedDict

from app.grounding import db
from app.grounding.normalize import normalize_greek


class _GazetteerData(TypedDict):
    """Shape of the module-level cache dict populated by `_load()`."""

    universities: list[str]
    departments: list[dict[str, str]]
    university_index: dict[str, list[str]]
    department_index: dict[str, list[dict[str, str]]]
    normalized_universities: list[tuple[str, str]]
    normalized_departments: list[tuple[str, str, str]]

# ---------------------------------------------------------------------------
# ACRONYM_MAP — hand-curated abbreviation → canonical evdx:name mapping
# ---------------------------------------------------------------------------
# Keys are the most common Greek university abbreviations exactly as users type
# them (uppercase Greek letters, no accents).  Values are the exact canonical
# `evdx:name` strings as they appear in the EvdoGraph KG (verified against
# live data in scripts/grounding_labels.json).
#
# WHY UPPERCASE KEYS?
#   Acronyms are conventionally written in uppercase Greek (ΑΠΘ, ΕΚΠΑ).  At
#   lookup time in linker.py the input is normalized first, but we keep these
#   keys in their natural form for readability.  linker.py normalizes the key
#   before lookup, so mixed-case or accented variants ("Απθ") still resolve.
ACRONYM_MAP: dict[str, str] = {
    "ΑΠΘ": "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ",
    "ΕΚΠΑ": "ΕΘΝΙΚΟ & ΚΑΠΟΔΙΣΤΡΙΑΚΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΑΘΗΝΩΝ",
    "ΕΜΠ": "ΕΘΝΙΚΟ ΜΕΤΣΟΒΙΟ ΠΟΛΥΤΕΧΝΕΙΟ",
    "ΟΠΑ": "ΟΙΚΟΝΟΜΙΚΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΑΘΗΝΩΝ",
    "ΔΠΘ": "ΔΗΜΟΚΡΙΤΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΡΑΚΗΣ",
    "ΠΑΜΑΚ": "ΠΑΝΕΠΙΣΤΗΜΙΟ ΜΑΚΕΔΟΝΙΑΣ",
    "ΕΑΠ": "ΕΛΛΗΝΙΚΟ ΑΝΟΙΧΤΟ ΠΑΝΕΠΙΣΤΗΜΙΟ",
    "ΓΠΑ": "ΓΕΩΠΟΝΙΚΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΑΘΗΝΩΝ",
    "ΠΑΝΤΕΙΟ": "ΠΑΝΤΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΚΟΙΝΩΝΙΚΩΝ ΚΑΙ ΠΟΛΙΤΙΚΩΝ ΕΠΙΣΤΗΜΩΝ",
    "ΠΑΠΕΙ": "ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΕΙΡΑΙΩΣ",
    "ΠΑΔΑ": "ΠΑΝΕΠΙΣΤΗΜΙΟ ΔΥΤΙΚΗΣ ΑΤΤΙΚΗΣ",
    "ΔΙΠΑΕ": "ΔΙΕΘΝΕΣ ΠΑΝΕΠΙΣΤΗΜΙΟ ΤΗΣ ΕΛΛΑΔΟΣ",
    "ΑΣΠΑΙΤΕ": "ΑΣΠΑΙΤΕ",
    "ΧΠ": "ΧΑΡΟΚΟΠΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ",
    "ΠΔΜ": "ΠΑΝΕΠΙΣΤΗΜΙΟ ΔΥΤΙΚΗΣ ΜΑΚΕΔΟΝΙΑΣ",
}

# ---------------------------------------------------------------------------
# Module-level cache — populated on first call to _load()
# ---------------------------------------------------------------------------

_cache: _GazetteerData | None = None  # None = not yet loaded


def _load() -> _GazetteerData:
    """Load and cache the gazetteer data from `entities.db`.

    On the first call, reads the `university` and `department` tables,
    deduplicates defensively, and builds normalized lookup indices. Every
    subsequent call skips I/O and returns the cached dict.

    The returned dict has four keys:
        `universities`     – list[str], 46 distinct canonical labels
        `departments`      – list[dict[str, str]], 799 distinct pairs
        `university_index` – dict[str, list[str]], normalized → [canonical_label, ...]
        `department_index` – dict[str, list[dict]], normalized → [{university, department}, ...]

    Returns
    -------
    dict
        The cached gazetteer data.

    Raises
    ------
    FileNotFoundError
        If `entities.db` is missing. See `db.get_connection`.
    """
    global _cache

    if _cache is not None:
        return _cache

    conn = db.get_connection()
    try:
        # --- 1. Read + dedup universities --------------------------------------
        # Defensive dedup: the builder script already writes distinct rows, but
        # this module should not assume that if entities.db was ever produced
        # some other way. `surface`/`parent` are the unified column names
        # schema.py uses for every entity class 
        # `university` has no `parent` (it is the top of the hierarchy).
        universities: list[str] = sorted(
            {row["surface"] for row in conn.execute("SELECT surface FROM university")}
        )

        # --- 2. Read + dedup department pairs -----------------------------------
        seen_pairs: set[tuple[str, str]] = set()
        departments: list[dict[str, str]] = []
        for row in conn.execute("SELECT parent, surface FROM department"):
            pair = (row["parent"], row["surface"])
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                departments.append({"university": row["parent"], "department": row["surface"]})
        departments.sort(key=lambda d: (d["university"], d["department"]))
    finally:
        conn.close()

    # --- 3. Build normalized university index -----------------------------------
    # Maps normalize_greek(canonical_label) → [canonical_label].
    # Most keys map to exactly one label; collisions are possible if two
    # universities normalize to the same string (unlikely but handled).
    university_index: dict[str, list[str]] = {}
    for uni in universities:
        key = normalize_greek(uni)
        university_index.setdefault(key, []).append(uni)

    # --- 4. Build normalized department index ------------------------------------
    # Maps normalize_greek(dept_name) → [{"university": ..., "department": ...}, ...].
    # normalize_greek strips parenthetical status suffixes like "(ΚΑΤΑΡΓΗΘΗΚΕ)"
    # so abolished departments are indexed under the same key as their active
    # counterpart — a deliberate choice so queries still resolve them.
    department_index: dict[str, list[dict[str, str]]] = {}
    for dept in departments:
        key = normalize_greek(dept["department"])
        department_index.setdefault(key, []).append(dept)

    # --- 5. Build normalized label lists (for linker._stage3_fuzzy) --------------
    # Precomputed here, once, so the fuzzy-matching stage never re-runs
    # normalize_greek over the whole gazetteer on every call — see module
    # docstring "NORMALIZED LABEL LISTS".
    normalized_universities: list[tuple[str, str]] = [
        (normalize_greek(uni), uni) for uni in universities
    ]
    normalized_departments: list[tuple[str, str, str]] = [
        (normalize_greek(dept["department"]), dept["department"], dept["university"])
        for dept in departments
    ]

    # --- 6. Populate cache and return ---------------------------------------------
    _cache = {
        "universities": universities,
        "departments": departments,
        "university_index": university_index,
        "department_index": department_index,
        "normalized_universities": normalized_universities,
        "normalized_departments": normalized_departments,
    }
    return _cache


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_universities() -> list[str]:
    """Return the list of 46 distinct canonical university labels from EvdoGraph.
    
    Returns
    -------
    list[str]
        46 canonical university name strings.
    """
    return _load()["universities"]


def get_departments() -> list[dict[str, str]]:
    """Return the list of 799 distinct department dicts from EvdoGraph.

    Each dict has exactly two keys:
        `university`  – the canonical university label (matches get_universities())
        `department`  – the canonical department label (may include status suffixes)

    The list is sorted by (university, department) and contains no duplicate
    (university, department) pairs.

    Returns
    -------
    list[dict[str, str]]
        799 dicts, each with `university` and `department` string keys.
    """
    return _load()["departments"]


def get_university_index() -> dict[str, list[str]]:
    """Return a normalized lookup index for university labels.

    The index maps `normalize_greek(canonical_label)` → `[canonical_label]`
    for every university in get_universities().  linker.py normalizes the
    user-typed entity mention and looks it up here to find the KG canonical form.

    Returns
    -------
    dict[str, list[str]]
        Mapping from normalized university label to a list of canonical labels
        that normalize to the same key.
    """
    return _load()["university_index"]


def get_department_index() -> dict[str, list[dict[str, str]]]:
    """Return a normalized lookup index for department labels.

    The index maps `normalize_greek(dept_name)` →
    `[{"university": ..., "department": ...}, ...]` for every department in
    get_departments().  Status suffixes (e.g. "(ΚΑΤΑΡΓΗΘΗΚΕ)")
    are stripped by normalize_greek before indexing, so abolished departments
    resolve under the same key as their active equivalent.

    Returns
    -------
    dict[str, list[dict[str, str]]]
        Mapping from normalized department name to a list of
        `{"university": str, "department": str}` dicts.
    """
    return _load()["department_index"]


def get_normalized_universities() -> list[tuple[str, str]]:
    """Return precomputed `(normalized_label, canonical_label)` pairs.

    For `linker._stage3_fuzzy`'s `rapidfuzz.process.extractOne` call —
    see module docstring "NORMALIZED LABEL LISTS" for why this exists as a
    cache rather than being rebuilt per call.

    Returns
    -------
    list[tuple[str, str]]
        One tuple per university, in the same order as `get_universities()`.
    """
    return _load()["normalized_universities"]


def get_normalized_departments() -> list[tuple[str, str, str]]:
    """Return precomputed `(normalized_label, canonical_dept, canonical_uni)` triples.

    For `linker._stage3_fuzzy`'s `rapidfuzz.process.extractOne` call —
    see module docstring "NORMALIZED LABEL LISTS" for why this exists as a
    cache rather than being rebuilt per call.

    Returns
    -------
    list[tuple[str, str, str]]
        One tuple per department, in the same order as `get_departments()`.
    """
    return _load()["normalized_departments"]
