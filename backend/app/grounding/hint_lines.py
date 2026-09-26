"""Markdown line formatters for the grounding hint block.

Turns a ``ResolvedEntity`` or ``TitleMatch`` into the one-line markdown
bullet ``build_grounding_hints`` assembles into its output block. Split out
(ADR-021) from ``hints.py`` — pure formatting, no orchestration logic.
"""

from __future__ import annotations

from collections.abc import Iterable

from app.grounding.lexicon import _TITLE_CLASS_LABELS
from app.grounding.linker import ResolvedEntity
from app.grounding.title_index import TitleMatch


def _format_entity_lines(entities: Iterable[ResolvedEntity]) -> list[str]:
    """Format resolved entities as markdown bullet lines, one per LABEL.

    University: ``- [University] CANONICAL_LABEL``
    Department: ``- [Department @ UNI_1 | UNI_2 | …] CANONICAL_LABEL``

    Departments are grouped by label because many universities use the same
    label ("ΝΟΣΗΛΕΥΤΙΚΗΣ" exists at 7): the label is what goes into the
    SPARQL, and the universities after "@" say where it exists. Every
    university is listed — never only the one the question names — so the
    hint cannot contradict the question and "other than X" questions still
    see every label (ADR-028). The universities are joined with " | ", the
    block's existing "alternatives" separator (see ``_format_title_line``).
    A label at a single university renders exactly as before branch 3.

    Order is deterministic (the LLM DiskCache key hashes the prompt): lines
    in first-occurrence order of their label, universities in input order.

    Args:
        entities: Resolved entities, one per (label, university) pair.

    Returns:
        Markdown bullet strings (no trailing newlines).
    """
    universities_by_label: dict[tuple[str, str], list[str]] = {}
    for entity in entities:
        key = (entity.entity_type, entity.canonical_label)
        parents = universities_by_label.setdefault(key, [])
        if entity.parent_university and entity.parent_university not in parents:
            parents.append(entity.parent_university)

    lines: list[str] = []
    for (entity_type, label), parents in universities_by_label.items():
        if entity_type == "university":
            lines.append(f"- [University] {label}")
        else:
            # Department — its universities give the SPARQL its context.
            lines.append(f"- [Department @ {' | '.join(parents) or 'unknown'}] {label}")
    return lines


def _format_title_line(match: TitleMatch) -> str:
    """Format a single title candidate as a class-tagged markdown bullet.

    One line per TITLE, not per surface form — multiple surface forms (e.g.
    the ALL-CAPS accent-free and mixed-case accented KG storage variants of
    the same title) are joined with " | ", the block's "variants of the same
    thing" separator (department lines use it for their universities too).

    Example: ``- [Course] "ΑΡΧΙΤΕΚΤΟΝΙΚΗ ΥΠΟΛΟΓΙΣΤΩΝ" | "Αρχιτεκτονική Υπολογιστών"``

    Args:
        match: A ``TitleMatch`` with its ``entity_class`` set.

    Returns:
        A markdown bullet string (no trailing newline).
    """
    label = _TITLE_CLASS_LABELS[match.entity_class]
    surfaces = " | ".join(f'"{s}"' for s in match.surface_forms)
    return f"- [{label}] {surfaces}"
