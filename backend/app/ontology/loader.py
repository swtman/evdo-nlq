"""
Loads the static EvdoGraph ontology summary from prompts/ontology-summary.md.

The ontology summary is a Markdown file that
describes the structure of the EvdoGraph knowledge graph: what classes exist
(e.g. University, Department, Course), what properties connect them, and example values.

This summary is injected into the system prompt of every LLM call. It gives
the LLM the vocabulary and structure it needs to write correct SPARQL
queries against EvdoGraph, without needing to query the database at runtime.

HOW THE MODULE-LEVEL CACHE WORKS
---------------------------------
`_cached` is a module-level variable (defined at the top of the file, outside
any function). The first time `load_summary()` is called, it reads the file
from disk and stores the text in `_cached`. Every subsequent call skips the
file read and returns the already-stored string directly.

This is the simplest possible cache: a single variable. It persists for the
entire lifetime of the running server process. Since the ontology summary never
changes while the server is running, this is perfectly safe.

"""

from __future__ import annotations

from pathlib import Path

# Absolute path to the ontology summary file, resolved relative to this
# source file so it works from any working directory.
_ONTOLOGY_FILE = Path(__file__).parent.parent.parent.parent / "prompts" / "ontology-summary.md"

# Module-level cache. Starts as None (nothing loaded yet).
# Set to the file contents on the first call to load_summary().
# `str | None` means the variable holds either a string or None.
_cached: str | None = None


def load_summary() -> str:
    """Return the ontology summary text, reading from disk only on the first call.

    After the first call the text is kept in `_cached` and returned instantly
    on every subsequent call.

    Returns
    -------
    str
        The full text of `prompts/ontology-summary.md`.

    Raises
    ------
    FileNotFoundError
        If the summary file is missing. This would mean the repo is in an
        unexpected state — the file is checked into git and should always
        be present.
    """
    global _cached

    if _cached is None:
        # First call — read from disk
        if not _ONTOLOGY_FILE.exists():
            raise FileNotFoundError(f"Ontology summary not found: {_ONTOLOGY_FILE}")
        _cached = _ONTOLOGY_FILE.read_text(encoding="utf-8")

    # Second and all subsequent calls skip straight here
    return _cached
