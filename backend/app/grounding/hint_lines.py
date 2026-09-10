"""Markdown line formatters for the grounding hint block.

Turns a ``ResolvedEntity`` or ``TitleMatch`` into the one-line markdown
bullet ``build_grounding_hints`` assembles into its output block. Split out
(ADR-021) from ``hints.py`` — pure formatting, no orchestration logic.
"""

from __future__ import annotations

from app.grounding.lexicon import _GREEK_VOWELS_STR, _TITLE_CLASS_LABELS, _VOWEL_TO_ACCENTED
from app.grounding.linker import ResolvedEntity
from app.grounding.title_index import TitleMatch


def _accent_last_vowel(stem: str) -> str | None:
    """Return stem with its last vowel accented, or None if no vowel found."""
    for i in reversed(range(len(stem))):
        if stem[i] in _GREEK_VOWELS_STR:
            return stem[:i] + stem[i].translate(_VOWEL_TO_ACCENTED) + stem[i + 1 :]
    return None


def _format_entity_line(entity: ResolvedEntity) -> str:
    """Format a single entity as a markdown bullet line.

    University: ``- [University] CANONICAL_LABEL``
    Department: ``- [Department @ PARENT_UNIVERSITY] CANONICAL_LABEL``

    Args:
        entity: A resolved entity from the linker.

    Returns:
        A markdown bullet string (no trailing newline).
    """
    if entity.entity_type == "university":
        return f"- [University] {entity.canonical_label}"
    # Department — include parent university for SPARQL context.
    parent = entity.parent_university or "unknown"
    return f"- [Department @ {parent}] {entity.canonical_label}"


def _format_title_line(match: TitleMatch) -> str:
    """Format a single resolved title as a class-tagged markdown bullet.

    One line per TITLE, not per surface form — multiple surface forms (e.g.
    the ALL-CAPS accent-free and mixed-case accented KG storage variants of
    the same title) are joined with " | ", reusing the convention the
    Topic-stems section already uses for "variants of the same thing", so
    the model isn't taught a second syntax for the same idea.

    Example: ``- [Course] "ΑΡΧΙΤΕΚΤΟΝΙΚΗ ΥΠΟΛΟΓΙΣΤΩΝ" | "Αρχιτεκτονική Υπολογιστών"``

    Args:
        match: A ``TitleMatch`` with its ``entity_class`` set.

    Returns:
        A markdown bullet string (no trailing newline).
    """
    label = _TITLE_CLASS_LABELS[match.entity_class]
    surfaces = " | ".join(f'"{s}"' for s in match.surface_forms)
    return f"- [{label}] {surfaces}"
