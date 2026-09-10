"""Title-corpus cleaning shared by ``build_entity_db.py`` and its tests.

WHY THIS IS A SEPARATE MODULE (not left inside ``scripts/build_entity_db.py``)
---------------------------------------------------------------------------------
Files under ``backend/scripts/`` are not importable from ``backend/tests/``
without ``sys.path`` manipulation. Moving the cleaning logic here makes it a
normal importable module, so the regression test in
``tests/test_grounding_clean.py`` needs no path hacks. ``clean_titles`` is
class-agnostic (the caller decides whether the titles are courses or books),
matching the fact that course and book titles get identical treatment.

THE BUG THIS MODULE FIXES
---------------------------
Course titles used to be cleaned by ``" ".join(raw_title.split())`` and the
result was stored as the ``surface`` value later emitted into SPARQL
``VALUES`` clauses. Python's argument-less ``str.split()`` treats any
Unicode whitespace as a separator, not just spaces and tabs — including
U+00A0 (NO-BREAK SPACE) and U+2008 (PUNCTUATION SPACE), both of which occur
inside real KG titles (e.g. copy-pasted from Word or a PDF). RDF matches
plain literals by exact code-point equality, so a title stored in the KG as
``"ΟΙΚΟΝΟΜΕΤΡΙΑ\xa0 ΙΙ"`` and rewritten by cleaning to
``"ΟΙΚΟΝΟΜΕΤΡΙΑ ΙΙ"`` before being bound in a ``VALUES`` clause matches ZERO
triples — silently. The search step reports a confident match, the LLM
writes syntactically valid SPARQL, and the query returns nothing. Measured
on the book corpus: 52 titles affected this way.

THE FIX
-------
``surface`` (what gets stored, and later bound in ``VALUES``) is now the RAW
KG literal, untouched. The whitespace-collapsed form is used ONLY to (a)
validate the title isn't empty/junk and (b) compute ``norm`` (the search key,
via ``normalize_greek``, which does its own whitespace collapsing as its
final step regardless). Because ``norm`` is unchanged by this fix, ranking
behavior — the FTS5 index, the bm25 candidate order, the rapidfuzz scores,
the acceptance threshold — is exactly what it was before. This is a pure
``surface``-column correctness fix, not a ranking change.

One consequence: two raw variants that previously collapsed into one
``surface`` (because they differed only in whitespace) now produce two
separate surface forms sharing one ``norm``. The ``VALUES`` clause lists
both — correct, since either could be the KG's real stored literal, at the
cost of a slightly longer hint line.

Titles containing a literal newline (``\\n``/``\\r``) are dropped rather than
stored: a newline would break both the one-bullet-per-line hint format
(``- "..."``) and the SPARQL string literal syntax, and a title with an
embedded newline is almost certainly corrupt data rather than a real title.

Display-side cleanup (the search UI showing a stray leading tab as visible
whitespace) is a presentation concern, not a data-integrity one — handled
separately in ``api/entities.py::_pick_display_surface``, which collapses
whitespace only for what's shown on screen. The database and the SPARQL
grounding path always carry the raw literal.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.grounding.normalize import normalize_greek


@dataclass
class DropCounts:
    """Itemized count of raw titles discarded by ``clean_titles``.

    Kept itemized (not a bare total) so the builder script's report can show
    why records were dropped — the module docstring of
    ``build_entity_db.py`` commits to reporting every drop; a single opaque
    count would not let a reader tell "9 mojibake records" apart from
    "9 titles that were somehow entirely whitespace".
    """

    mojibake: int = 0
    empty: int = 0
    newline: int = 0

    @property
    def total(self) -> int:
        return self.mojibake + self.empty + self.newline


def clean_titles(raw_titles: list[str]) -> tuple[dict[str, set[str]], DropCounts]:
    """Clean and group raw KG titles (course or book) by their normalized key.

    Args:
        raw_titles: Raw ``evdx:title`` strings as returned by SPARQL, for
                    either ``evdx:Course`` or ``evdx:Book`` nodes
                    the cleaning rules are identical for both classes.

    Returns:
        A tuple of:
          - ``surface_map``: ``normalize_greek(collapsed title) ->
            {raw surface form, ...}``. Values are the RAW, unmodified KG
            literals — see module docstring for why.
          - ``drops``: itemized counts of discarded raw titles.
    """
    surface_map: dict[str, set[str]] = {}
    drops = DropCounts()

    for raw in raw_titles:
        # Checked on the RAW string, before whitespace-collapsing — collapsing
        # via str.split() would itself remove a newline, hiding the very thing
        # this check exists to catch.
        if "\n" in raw or "\r" in raw:
            drops.newline += 1
            continue
        if "�" in raw:  # U+FFFD REPLACEMENT CHARACTER — mojibake/encoding corruption
            drops.mojibake += 1
            continue

        # Collapsed form: validation + the norm (search) key ONLY. Never stored.
        collapsed = " ".join(raw.split())
        if not collapsed:
            drops.empty += 1
            continue

        norm = normalize_greek(collapsed)
        if not norm:
            drops.empty += 1
            continue

        surface_map.setdefault(norm, set()).add(raw)  # RAW, untouched

    return surface_map, drops
