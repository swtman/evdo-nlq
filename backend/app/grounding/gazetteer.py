"""Entity label store for the grounding module.

WHAT IS THE GAZETTEER?
----------------------
A gazetteer is a geographical/entity reference dictionary.  Here it holds the
canonical university and department names as they appear in the EvdoGraph KG
(field ``evdx:name`` values), plus a hand-curated map of common Greek university
abbreviations to their full canonical forms.

WHY A GAZETTEER?
----------------
The EvdoGraph KG stores names in ALL-CAPS, accent-free Greek strings, e.g.
"ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ".  Users typically type abbreviated or
accented variants ("ΑΠΘ", "Αριστοτέλειο").  The gazetteer gives the linker
(linker.py) the canonical forms it needs to resolve user mentions to exact KG
labels — which then get injected into the SPARQL query.

DATA SOURCE
-----------
Labels are loaded from ``scripts/grounding_labels.json`` at the repo root.  That
file is a snapshot extracted from a live EvdoGraph SPARQL query; it contains
duplicate entries (the same university appears once per book in the dataset).
We dedup on load so callers always work with distinct labels.

MODULE-LEVEL CACHE
------------------
All public functions delegate to ``_load()``, which populates ``_cache`` on the
first call and returns the cached dict on every subsequent call.  This mirrors
the pattern in ``app/ontology/loader.py``: one file read per process lifetime.

NORMALIZED LOOKUP INDEX
-----------------------
``get_university_index()`` and ``get_department_index()`` return dicts keyed on
``normalize_greek(label)`` so that linker.py can perform accent/case-insensitive
lookups without re-normalizing on every query.  Department labels include
parenthetical status suffixes in the raw data (e.g. "(ΚΑΤΑΡΓΗΘΗΚΕ)"); the index
key is built after ``normalize_greek`` has stripped those suffixes, so abolished
departments are still reachable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

from app.grounding.normalize import normalize_greek


class _GazetteerData(TypedDict):
    """Shape of the module-level cache dict populated by ``_load()``."""

    universities: list[str]
    departments: list[dict[str, str]]
    university_index: dict[str, list[str]]
    department_index: dict[str, list[dict[str, str]]]

# Path to the labels snapshot: 4 .parent calls walk from
#   backend/app/grounding/gazetteer.py → backend/app/grounding/ → backend/app/
#   → backend/ → repo root, then down into scripts/.
_LABELS_FILE = (
    Path(__file__).parent.parent.parent.parent / "scripts" / "grounding_labels.json"
)

# ---------------------------------------------------------------------------
# ACRONYM_MAP — hand-curated abbreviation → canonical evdx:name mapping
# ---------------------------------------------------------------------------
# Keys are the most common Greek university abbreviations exactly as users type
# them (uppercase Greek letters, no accents).  Values are the exact canonical
# ``evdx:name`` strings as they appear in the EvdoGraph KG (verified against
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
    """Load and cache the gazetteer data from disk.

    On the first call, reads ``scripts/grounding_labels.json``, deduplicates
    the raw university list and department pairs, and builds normalized lookup
    indices.  Every subsequent call skips I/O and returns the cached dict.

    The returned dict has four keys:
        ``universities``      – list[str], 46 distinct canonical labels
        ``departments``       – list[dict[str, str]], 799 distinct pairs
        ``university_index``  – dict[str, list[str]], normalized → [canonical_label, ...]
        ``department_index``  – dict[str, list[dict]], normalized → [{university, department}, ...]

    Returns
    -------
    dict
        The cached gazetteer data.

    Raises
    ------
    FileNotFoundError
        If ``scripts/grounding_labels.json`` is missing.  The file is checked
        into git and should always be present.
    """
    global _cache

    if _cache is not None:
        return _cache

    # --- 1. Read raw data from disk -------------------------------------------
    if not _LABELS_FILE.exists():
        raise FileNotFoundError(
            f"Gazetteer labels file not found: {_LABELS_FILE}\n"
            "Run scripts/dump_labels.py to regenerate it."
        )

    raw = json.loads(_LABELS_FILE.read_text(encoding="utf-8"))

    # --- 2. Deduplicate universities -------------------------------------------
    # The JSON has 133 raw entries (same university repeated once per book).
    # Use a set to get 46 distinct labels, then sort for stable ordering.
    universities: list[str] = sorted(set(raw["universities"]))

    # --- 3. Deduplicate department pairs ---------------------------------------
    # The JSON has 2483 raw dicts; many are duplicates.  A (university, dept)
    # tuple uniquely identifies a pair — use a set to get 799 distinct pairs.
    seen_pairs: set[tuple[str, str]] = set()
    departments: list[dict[str, str]] = []
    for entry in raw["departments"]:
        pair = (entry["university"], entry["department"])
        if pair not in seen_pairs:
            seen_pairs.add(pair)
            departments.append(
                {"university": entry["university"], "department": entry["department"]}
            )

    # Sort for stable ordering (by university then department name)
    departments.sort(key=lambda d: (d["university"], d["department"]))

    # --- 4. Build normalized university index ---------------------------------
    # Maps normalize_greek(canonical_label) → [canonical_label].
    # Most keys map to exactly one label; collisions are possible if two
    # universities normalize to the same string (unlikely but handled).
    university_index: dict[str, list[str]] = {}
    for uni in universities:
        key = normalize_greek(uni)
        university_index.setdefault(key, []).append(uni)

    # --- 5. Build normalized department index ---------------------------------
    # Maps normalize_greek(dept_name) → [{"university": ..., "department": ...}, ...].
    # normalize_greek strips parenthetical status suffixes like "(ΚΑΤΑΡΓΗΘΗΚΕ)"
    # so abolished departments are indexed under the same key as their active
    # counterpart — a deliberate choice so queries still resolve them.
    department_index: dict[str, list[dict[str, str]]] = {}
    for dept in departments:
        key = normalize_greek(dept["department"])
        department_index.setdefault(key, []).append(dept)

    # --- 6. Populate cache and return -----------------------------------------
    _cache = {
        "universities": universities,
        "departments": departments,
        "university_index": university_index,
        "department_index": department_index,
    }
    return _cache


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_universities() -> list[str]:
    """Return the list of 46 distinct canonical university labels from EvdoGraph.

    Labels are the exact ``evdx:name`` strings stored in the KG — ALL-CAPS,
    accent-free Greek.  The list is sorted alphabetically and contains no
    duplicates (deduped from the raw JSON on first load).

    Returns
    -------
    list[str]
        46 canonical university name strings.
    """
    return _load()["universities"]


def get_departments() -> list[dict[str, str]]:
    """Return the list of 799 distinct department dicts from EvdoGraph.

    Each dict has exactly two keys:
        ``university``  – the canonical university label (matches get_universities())
        ``department``  – the canonical department label (may include status suffixes)

    The list is sorted by (university, department) and contains no duplicate
    (university, department) pairs.

    Returns
    -------
    list[dict[str, str]]
        799 dicts, each with ``university`` and ``department`` string keys.
    """
    return _load()["departments"]


def get_university_index() -> dict[str, list[str]]:
    """Return a normalized lookup index for university labels.

    The index maps ``normalize_greek(canonical_label)`` → ``[canonical_label]``
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

    The index maps ``normalize_greek(dept_name)`` →
    ``[{"university": ..., "department": ...}, ...]`` for every department in
    get_departments().  Status suffixes (e.g. "(ΚΑΤΑΡΓΗΘΗΚΕ)")
    are stripped by normalize_greek before indexing, so abolished departments
    resolve under the same key as their active equivalent.

    Returns
    -------
    dict[str, list[dict[str, str]]]
        Mapping from normalized department name to a list of
        ``{"university": str, "department": str}`` dicts.
    """
    return _load()["department_index"]
