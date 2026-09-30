"""Tests for prompt nl-to-sparql-v9 (branch feat/span-title-linking, ADR-035).

v9 forks v8 and changes ONE thing (one change per prompt version, so an eval difference
has one cause): Rule 16 gains a "Named titles" bullet. Branch 6's grounding puts a title
the question names with an explicit cue («ονομάζεται», «με τίτλο», «…») under its own
`**Named titles**:` header (decision 1: a cue makes the binding firm) and emits no topic
stems for its words; un-cued titles stay "Title candidates" and v8's text for them is
unchanged.
"""

from app.pipeline.query_pipeline import PROMPT_VERSION
from app.prompts.loader import load, load_user_template

_NAMED_BULLET_START = "- **Named titles**:"


def _named_titles_bullet(version: int) -> str:
    """The whole bullet line, from its indentation to its newline."""
    system = load("nl-to-sparql", version)
    at = system.index(_NAMED_BULLET_START)
    start = system.rfind("\n", 0, at) + 1
    return system[start : system.index("\n", at) + 1]


def test_production_prompt_is_v9() -> None:
    assert PROMPT_VERSION == 9


def test_v9_keeps_the_cacheable_layout() -> None:
    """Same slot layout as v6–v8 (ADR-026): static system, hints in the user message."""
    system = load("nl-to-sparql", 9)
    assert "{ontology_summary}" in system and "{few_shot_block}" in system
    assert "{grounding_hints}" not in system
    assert load_user_template("nl-to-sparql", 9) == load_user_template("nl-to-sparql", 8)


def test_v9_named_titles_bullet_says_bind_with_values() -> None:
    bullet = _named_titles_bullet(9)
    assert "**Named titles**" in bullet
    assert "VALUES" in bullet
    assert "Title candidates" in bullet  # says how it differs from the candidates


def test_v9_adds_only_the_named_titles_bullet() -> None:
    """Outside the new bullet, v9's system text is v8's, character for character."""
    assert _NAMED_BULLET_START not in load("nl-to-sparql", 8)
    assert load("nl-to-sparql", 9).replace(_named_titles_bullet(9), "") == load("nl-to-sparql", 8)


def test_v9_named_bullet_comes_before_title_candidates() -> None:
    system = load("nl-to-sparql", 9)
    assert system.index(_NAMED_BULLET_START) < system.index("- **Title candidates**:")
