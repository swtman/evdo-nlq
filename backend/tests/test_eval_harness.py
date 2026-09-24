"""Tests for scripts/eval.py — the eval harness (branch fix/eval-harness-grounded-prompts).

Finding C17 of the title-linking plan: the harness accepted --prompt-version 1-4
only and built ONE fixed system prompt without per-question grounding hints, so
the production prompt (v5/v6, grounded) could never be evaluated. These tests pin
the fix: grounded prompt versions are built per question by the SAME builder
production uses (QueryPipeline._build_system), and the report records what data
the grounding used.

scripts/ is not a package, so the module is loaded from its file path.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.pipeline.query_pipeline import PROMPT_VERSION, QueryPipeline

_EVAL_PATH = Path(__file__).resolve().parent.parent / "scripts" / "eval.py"


@pytest.fixture(scope="module")
def harness():
    spec = importlib.util.spec_from_file_location("eval_harness", _EVAL_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _capture_system(pipeline, question: str) -> str:
    """Run the harness pipeline with the LLM call stubbed, return the system prompt it used."""
    seen: dict[str, str] = {}

    def fake_generate(system, q, ontology):
        seen["system"] = system
        return "SELECT * WHERE { ?s ?p ?o }", 0, 0, 0

    pipeline._generate_with_retry = fake_generate  # instance attribute shadows the method
    pipeline.run(question)
    return seen["system"]


def test_production_prompt_versions_are_selectable(harness) -> None:
    versions = harness._available_prompt_versions()
    assert {5, 6} <= set(versions)
    assert PROMPT_VERSION in versions


def test_grounded_version_detected_from_template(harness) -> None:
    assert harness._is_grounded(6) and harness._is_grounded(5)
    assert not harness._is_grounded(4)


def test_grounded_prompt_is_built_per_question_like_production(harness) -> None:
    question = "ποια βιβλία προτείνει το ΑΠΘ;"
    pipeline = harness._build_pipeline(PROMPT_VERSION, "fake", "fake-v1")
    system = _capture_system(pipeline, question)

    # grounding hints for THIS question are present …
    assert "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" in system
    # … and the prompt is byte-identical to what production builds
    production = QueryPipeline(pipeline._provider, pipeline._sparql_client, "fake", "fake-v1")
    assert system == production._build_system(question)


def test_grounded_prompt_differs_between_questions(harness) -> None:
    pipeline = harness._build_pipeline(PROMPT_VERSION, "fake", "fake-v1")
    a = _capture_system(pipeline, "ποια βιβλία προτείνει το ΑΠΘ;")
    b = _capture_system(pipeline, "ποια βιβλία αλγορίθμων υπάρχουν;")
    assert a != b


def test_legacy_version_keeps_fixed_ungrounded_prompt(harness) -> None:
    pipeline = harness._build_pipeline(4, "fake", "fake-v1")
    a = _capture_system(pipeline, "ποια βιβλία προτείνει το ΑΠΘ;")
    b = _capture_system(pipeline, "ποια βιβλία αλγορίθμων υπάρχουν;")
    assert a == b
    assert "Resolved entities" not in a


def test_pipeline_prompt_version_is_configurable() -> None:
    from unittest.mock import MagicMock

    from app.llm.fake_provider import FakeProvider
    from app.sparql.client import SparqlClient

    v5 = QueryPipeline(FakeProvider(), MagicMock(spec=SparqlClient), "fake", "fake-v1", prompt_version=5)
    v6 = QueryPipeline(FakeProvider(), MagicMock(spec=SparqlClient), "fake", "fake-v1")
    q = "ποια βιβλία προτείνει το ΑΠΘ;"
    assert "## Examples" not in v5._build_system(q)  # v5 has no few-shot slot
    assert "## Examples" in v6._build_system(q)


def test_report_provenance_records_grounding_inputs(harness) -> None:
    report = harness._render_report(
        [],
        prompt_version=6,
        provider="fake",
        model="fake-v1",
        language="greek",
        run_at="2026-09-24T12:00",
        git_sha="abc1234",
        prompt_sha="p" * 12,
        examples_sha="e" * 12,
        examples_name="eval-titles.yaml",
        grounded=True,
        entities_db="d" * 12 + " (snapshot 2026-09-24)",
    )
    assert "eval-titles.yaml" in report
    assert "entities.db" in report and "snapshot 2026-09-24" in report
    assert "per-question grounding" in report
