"""Tests for scripts/eval.py — the eval harness (branch fix/eval-harness-grounded-prompts).

Finding C17 of the title-linking plan: the harness accepted --prompt-version 1-4
only and built ONE fixed system prompt without per-question grounding hints, so
the production prompt (v5/v6, grounded) could never be evaluated. These tests pin
the fix: grounded prompt versions are built per question by the SAME builder
production uses (QueryPipeline._build_prompt — system + user message, ADR-026),
and the report records what data
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


def _capture_prompt(pipeline, question: str) -> tuple[str, str]:
    """Run the harness pipeline with the LLM call stubbed; return the (system, user) it sent."""
    seen: dict[str, str] = {}

    def fake_generate(system, user, ontology):
        seen["system"], seen["user"] = system, user
        return "SELECT * WHERE { ?s ?p ?o }", 0, 0, 0

    pipeline._generate_with_retry = fake_generate  # instance attribute shadows the method
    pipeline.run(question)
    return seen["system"], seen["user"]


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
    system, user = _capture_prompt(pipeline, question)

    # grounding hints for THIS question are present (in the user message since ADR-026) …
    assert "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" in user
    # … and the prompt pair is byte-identical to what production builds
    production = QueryPipeline(pipeline._provider, pipeline._sparql_client, "fake", "fake-v1")
    assert (system, user) == production._build_prompt(question)


def test_grounded_prompt_per_question_in_user_static_system(harness) -> None:
    pipeline = harness._build_pipeline(PROMPT_VERSION, "fake", "fake-v1")
    system_a, user_a = _capture_prompt(pipeline, "ποια βιβλία προτείνει το ΑΠΘ;")
    system_b, user_b = _capture_prompt(pipeline, "ποια βιβλία αλγορίθμων υπάρχουν;")
    assert user_a != user_b      # per-question part differs …
    assert system_a == system_b  # … the cacheable system prompt does not (ADR-026)


def test_legacy_version_keeps_fixed_ungrounded_prompt(harness) -> None:
    pipeline = harness._build_pipeline(4, "fake", "fake-v1")
    system_a, user_a = _capture_prompt(pipeline, "ποια βιβλία προτείνει το ΑΠΘ;")
    system_b, _ = _capture_prompt(pipeline, "ποια βιβλία αλγορίθμων υπάρχουν;")
    assert system_a == system_b
    assert "Resolved entities" not in system_a
    assert user_a == "ποια βιβλία προτείνει το ΑΠΘ;"


def test_pipeline_prompt_version_is_configurable() -> None:
    from unittest.mock import MagicMock

    from app.llm.fake_provider import FakeProvider
    from app.sparql.client import SparqlClient

    v5 = QueryPipeline(FakeProvider(), MagicMock(spec=SparqlClient), "fake", "fake-v1", prompt_version=5)
    v6 = QueryPipeline(FakeProvider(), MagicMock(spec=SparqlClient), "fake", "fake-v1")
    q = "ποια βιβλία προτείνει το ΑΠΘ;"
    assert "## Examples" not in v5._build_prompt(q)[0]  # v5 has no few-shot slot
    assert "## Examples" in v6._build_prompt(q)[0]


def test_report_provenance_records_grounding_inputs(harness) -> None:
    report = harness._render_report(
        [],
        prompt_version=6,
        provider="fake",
        model="fake-v1",
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


# ---------------------------------------------------------------------------
# Greek only (branch 4b, ADR-033 — title-linking plan decision 6)
# ---------------------------------------------------------------------------


def test_report_header_still_says_greek(harness) -> None:
    """Reports keep the word "greek" in the header (and file name) so they line up with the
    earlier `-greek-` runs, although there is no language choice any more."""
    report = harness._render_report(
        [],
        prompt_version=8,
        provider="fake",
        model="fake-v1",
        run_at="2026-09-26T12:00",
        git_sha="abc1234",
        prompt_sha="p" * 12,
        examples_sha="e" * 12,
    )
    assert report.splitlines()[0].startswith("# Eval Report — prompt v8 | fake/fake-v1 | greek |")


def test_language_option_is_gone(harness) -> None:
    """Users ask in Greek only: `--language` (and its default `both`, which ran every example
    twice) no longer exists."""
    parser = harness._build_arg_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["--language", "greek"])
    assert not hasattr(parser.parse_args([]), "language")


def test_example_without_an_english_question_runs(harness) -> None:
    """An example with only `question_greek` runs once, with that question, and the record
    carries no language field."""
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    pipeline = MagicMock()
    pipeline.run.return_value = SimpleNamespace(
        sparql="# NOT_ANSWERABLE: no such data", input_tokens=0, output_tokens=0
    )
    example = {
        "id": "ex-x",
        "query_shape": "not-answerable",
        "comparison_mode": "not-answerable",
        "question_greek": "Ποιος είναι ο καιρός;",
        "gold_sparql": "# NOT_ANSWERABLE: x",
    }
    result = harness._eval_example(example, pipeline, MagicMock())
    pipeline.run.assert_called_once_with("Ποιος είναι ο καιρός;")
    assert result["result_match"] is True
    assert "language" not in result
