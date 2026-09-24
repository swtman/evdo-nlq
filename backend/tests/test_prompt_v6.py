"""Tests for prompt nl-to-sparql-v6 and its use by the pipeline (branch 1).

v6 forks v5 (decision C1 of the title-linking plan): Rule 16 treats matched
titles as candidates, the hint-usage instructions moved here from hints.py,
and the {few_shot_block} slot is restored — v5 had none, so the few-shot
examples the pipeline passed were silently dropped by fill().
"""

from unittest.mock import MagicMock

from app.llm.fake_provider import FakeProvider
from app.pipeline.query_pipeline import QueryPipeline
from app.prompts.loader import load
from app.sparql.client import SparqlClient


def test_v6_has_all_three_slots() -> None:
    text = load("nl-to-sparql", 6)
    for slot in ("{ontology_summary}", "{grounding_hints}", "{few_shot_block}"):
        assert slot in text, slot


def test_v6_rule16_explains_title_candidates() -> None:
    text = load("nl-to-sparql", 6)
    assert "Title candidates" in text
    assert "Topic stems" in text
    # the usage instructions removed from hints.py now live in the prompt
    assert "evdx:hasBook" in text


def test_v5_still_loadable_for_ab_comparison() -> None:
    assert "{grounding_hints}" in load("nl-to-sparql", 5)


def test_pipeline_system_prompt_contains_few_shot_examples() -> None:
    pipeline = QueryPipeline(FakeProvider(), MagicMock(spec=SparqlClient), "fake", "fake-v1")
    system = pipeline._build_system("ποια βιβλία προτείνει το ΑΠΘ;")
    assert "## Examples" in system
    assert "### Example 1" in system
    assert "{few_shot_block}" not in system  # slot was filled, not left raw
