"""Loads the static EvdoGraph ontology summary from prompts/ontology-summary.md.

The summary is read once and cached in a module-level variable for the process lifetime.
No SPARQL is executed at startup — the ontology does not change.
"""
from __future__ import annotations

from pathlib import Path

_ONTOLOGY_FILE = Path(__file__).parent.parent.parent.parent / "prompts" / "ontology-summary.md"

_cached: str | None = None


def load_summary() -> str:
    """Return the compact ontology schema string. Cached after first read."""
    global _cached
    if _cached is None:
        if not _ONTOLOGY_FILE.exists():
            raise FileNotFoundError(f"Ontology summary not found: {_ONTOLOGY_FILE}")
        _cached = _ONTOLOGY_FILE.read_text(encoding="utf-8")
    return _cached
