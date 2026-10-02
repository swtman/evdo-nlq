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


def test_split_filter_keeps_items_without_a_split(harness) -> None:
    """--split selects the title eval set's dev or test items (ADR-034); examples.yaml items have no
    split and always run."""
    examples = [{"id": "a", "split": "dev"}, {"id": "b", "split": "test"}, {"id": "c"}]
    assert [e["id"] for e in harness._filter_split(examples, "dev")] == ["a", "c"]
    assert [e["id"] for e in harness._filter_split(examples, "test")] == ["b", "c"]
    assert [e["id"] for e in harness._filter_split(examples, None)] == ["a", "b", "c"]
    with pytest.raises(SystemExit):
        harness._build_arg_parser().parse_args(["--split", "train"])


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


# ---------------------------------------------------------------------------
# Three metrics, leakage, re-score, repeated runs (branch feat/eval-metrics, ADR-038)
# ---------------------------------------------------------------------------


def _res(columns, *rows, boolean=None):
    from app.sparql.client import SparqlResult

    return SparqlResult(
        columns=columns, rows=[dict(zip(columns, r, strict=True)) for r in rows], boolean=boolean
    )


def _rec(item_id, strict, intent, f1, *, shape="s", kind="list", cause=None, shown=False):
    """A result record as _eval_example returns it."""
    return {
        "id": item_id, "query_shape": shape, "question": "q", "gold_sparql": "SELECT ?x {}",
        "generated_sparql": "SELECT ?x {}", "result_match": strict, "intent_match": intent,
        "precision": 1.0, "recall": f1, "f1": f1, "answer_kind": kind, "cause": cause,
        "shown": shown, "title_offered": None, "ast_match": None, "error": None,
        "broken_gold": False, "input_tokens": 0, "output_tokens": 0, "duration_s": 0.0,
    }


def _render(harness, results, **extra):
    return harness._render_report(
        results, prompt_version=9, provider="fake", model="fake-v1", run_at="2026-10-02T12:00",
        git_sha="abc1234", prompt_sha="p" * 12, examples_sha="e" * 12, **extra,
    )


def test_shown_ids_only_for_the_few_shot_bank(harness) -> None:
    """Leakage (ADR-038): items the prompt SHOWS as worked examples are not scored. Only the
    few-shot bank can leak, and only into prompts that have a {few_shot_block} slot."""
    from app.prompts.examples_loader import few_shot_ids

    bank = harness._EXAMPLES_PATH
    titles = harness._REPO_ROOT / "prompts" / "eval-titles.yaml"
    assert {"ex-001", "ex-002", "ex-015", "ex-019"} <= set(harness._shown_ids(PROMPT_VERSION, bank))
    assert harness._shown_ids(4, bank) == few_shot_ids(6)  # v2–v4: fixed prompt, k = 6
    assert harness._shown_ids(5, bank) == []  # v5 had no few-shot slot (ADR-022)
    assert harness._shown_ids(1, bank) == []
    assert harness._shown_ids(PROMPT_VERSION, titles) == []


def test_headline_is_macro_f1_over_held_out_items(harness) -> None:
    """Macro F1 QALD is the headline (user decision 2026-10-02: the established KGQA metric —
    QALD-9, TEXT2SPARQL'25); it is the first, bold row, followed by intent and strict."""
    results = [
        _rec("ex-a", True, True, 1.0, shown=True),
        _rec("ex-b", True, True, 1.0),
        _rec("ex-c", False, True, 1.0, cause="column order"),
        _rec("ex-d", False, False, 0.5, cause="wrong rows (partial)"),
    ]
    report = _render(harness, results, shown_ids=["ex-a"])
    lines = report.splitlines()
    table = lines[lines.index("| Metric | Value | 95% interval |") + 2:]
    assert table[0].startswith("| Macro F1 QALD (headline)")
    assert table[1].startswith("| Intent-based match")
    assert table[2].startswith("| Strict execution match")
    f1, intent, strict = table[:3]
    bridge = next(x for x in lines if "pre-ADR-038" in x)
    assert "**0.83**" in f1 and "–" in f1  # (1 + 1 + 0.5) / 3; the 95% interval column is filled
    assert "2/3" in intent and "**" not in intent
    assert "1/3" in strict
    assert "2/4" in bridge  # strict over every item, the old basis
    assert "ex-a" in report.split("## Shown in the prompt")[1].split("\n## ")[0]


def test_report_sections_and_per_example_status(harness) -> None:
    results = [
        _rec("ex-c", False, True, 1.0, cause="column order", kind="count"),
        _rec("ex-d", False, False, 0.0, cause="wrong rows"),
        _rec("ex-a", True, True, 1.0, shown=True),
    ]
    report = _render(harness, results, shown_ids=["ex-a"])
    assert "## Per answer type" in report and "| count |" in report
    causes = report.split("## Error analysis by cause")[1].split("\n## ")[0]
    assert "column order" in causes and "ex-c" in causes and "wrong rows" in causes
    assert "### [PASS] ex-c" in report  # the header shows the headline (intent) verdict
    assert "### [FAIL] ex-d" in report
    assert "shown in prompt (not scored)" in report.split("### [PASS] ex-a")[1].splitlines()[0]


def test_eval_example_scores_all_three_metrics(harness) -> None:
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    gold_q, gen_q = "SELECT ?t WHERE { ?s ?p ?t }", "SELECT ?t ?n WHERE { ?s ?p ?t } LIMIT 20"
    pipeline = MagicMock()
    pipeline.run.return_value = SimpleNamespace(sparql=gen_q, input_tokens=1, output_tokens=2)
    client = MagicMock()
    answers = {
        gold_q: _res(["t"], ("A",), ("B",)),
        gen_q.removesuffix(" LIMIT 20"): _res(["n", "t"], ("1", "A"), ("2", "B"), ("2", "B")),
    }
    client.execute.side_effect = lambda q: answers[q]
    example = {"id": "ex-x", "query_shape": "s", "comparison_mode": "set",
               "question_greek": "q", "gold_sparql": gold_q}
    r = harness._eval_example(example, pipeline, client)
    assert r["result_match"] is False and r["intent_match"] is True
    assert r["f1"] == 1.0 and r["answer_kind"] == "list" and r["cause"] == "extra columns"


def test_said_not_answerable_on_an_answerable_item(harness) -> None:
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    pipeline = MagicMock()
    pipeline.run.return_value = SimpleNamespace(
        sparql="# NOT_ANSWERABLE: no", input_tokens=0, output_tokens=0
    )
    client = MagicMock()
    client.execute.return_value = _res(["t"], ("A",))
    example = {"id": "ex-x", "query_shape": "s", "comparison_mode": "set",
               "question_greek": "q", "gold_sparql": "SELECT ?t {}"}
    r = harness._eval_example(example, pipeline, client)
    client.execute.assert_called_once_with("SELECT ?t {}")  # the comment is never executed
    assert (r["result_match"], r["intent_match"]) == (False, False)
    assert (r["precision"], r["recall"], r["f1"]) == (1.0, 0.0, 0.0)  # an empty answer (QALD)
    assert r["cause"] == "said not answerable"


_OLD_REPORT = """# Eval Report — prompt v9 | claude/claude-haiku-4-5 | greek | 2026-09-30T10:00

## Provenance

| Field | Value |
|---|---|
| git HEAD | `abc1234` |
| nl-to-sparql-v9.md sha256[:12] | `ppp` |
| eval-titles.yaml sha256[:12] | `eee` |

## Per-example results

### [PASS] te-001 — title-course-at-university
**Q:** q1
<details><summary>Generated SPARQL</summary>

```sparql
SELECT ?t WHERE { ?s ?p ?t }
```
</details>

### [FAIL] te-002 — title-course-at-university
**Q:** q2
**Error:** `Pipeline error: boom`

### [FAIL] te-003 — x
<details><summary>Gold SPARQL</summary>

```sparql
SELECT ?gold WHERE { ?s ?p ?gold }
```
</details>
<details><summary>Generated SPARQL</summary>

```sparql
SELECT ?gen WHERE { ?s ?p ?gen }
```
</details>

### [PASS] ex-019 — not-answerable · shown in prompt (not scored)
<details><summary>Generated SPARQL</summary>

```sparql
# NOT_ANSWERABLE: weather
```
</details>
"""


def test_rescore_parses_an_existing_report(harness) -> None:
    meta, generated = harness._parse_report(_OLD_REPORT)
    assert meta == {"prompt_version": 9, "provider": "claude", "model": "claude-haiku-4-5",
                    "examples_name": "eval-titles.yaml", "examples_sha": "eee"}
    assert generated == {
        "te-001": "SELECT ?t WHERE { ?s ?p ?t }",
        "te-002": None,
        "te-003": "SELECT ?gen WHERE { ?s ?p ?gen }",
        "ex-019": "# NOT_ANSWERABLE: weather",
    }


def test_rescore_scores_without_an_llm(harness) -> None:
    from unittest.mock import MagicMock

    client = MagicMock()
    answers = {"G": _res(["t"], ("A",), ("B",)), "S": _res(["t"], ("A",), ("B",), ("B",))}
    client.execute.side_effect = lambda q: answers[q]
    examples = [
        {"id": "a", "query_shape": "s", "comparison_mode": "set", "question_greek": "q",
         "gold_sparql": "G"},
        {"id": "na", "query_shape": "n", "comparison_mode": "not-answerable",
         "question_greek": "q", "gold_sparql": "# NOT_ANSWERABLE: x"},
        {"id": "gone", "query_shape": "s", "comparison_mode": "set", "question_greek": "q",
         "gold_sparql": "G"},
    ]
    results = harness._rescore(examples, {"a": "S LIMIT 5", "na": "# NOT_ANSWERABLE: y"}, client)
    by_id = {r["id"]: r for r in results}
    assert set(by_id) == {"a", "na"}  # items absent from the report are not invented
    assert (by_id["a"]["result_match"], by_id["a"]["intent_match"]) == (False, True)
    assert by_id["a"]["cause"] == "duplicate rows" and by_id["a"]["title_offered"] is None
    assert by_id["na"]["intent_match"] is True and by_id["na"]["f1"] == 1.0


def test_runs_above_one_need_no_cache(harness) -> None:
    """Cached re-runs replay the same answers — N runs would show zero variance (ADR-038)."""
    args = harness._build_arg_parser().parse_args(["--runs", "3", "--provider", "fake"])
    with pytest.raises(SystemExit, match="--no-cache"):
        harness._run(args)
    assert harness._build_arg_parser().parse_args([]).runs == 1


def test_json_sidecar_carries_every_score(harness) -> None:
    import json

    doc = harness._report_json([_rec("ex-a", True, True, 1.0, shown=True)], {"prompt_version": 9})
    item = json.loads(json.dumps(doc, ensure_ascii=False))["items"][0]
    for key in ("id", "result_match", "intent_match", "precision", "recall", "f1",
                "answer_kind", "cause", "shown", "title_offered", "generated_sparql"):
        assert key in item
    assert doc["meta"]["prompt_version"] == 9


def test_runs_summary_reports_spread_and_stability(harness) -> None:
    runs = [
        [_rec("a", True, True, 1.0), _rec("b", False, False, 0.0)],
        [_rec("a", True, True, 1.0), _rec("b", True, True, 1.0)],
    ]
    summary = harness._render_runs_summary(runs, title="fake/fake-v1", shown_ids=[])
    assert "mean" in summary.lower()
    assert "| b | 0.50 | 1/2 |" in summary and "| a | 1.00 | 2/2 |" in summary  # F1 first
    spread = summary.split("## Spread across runs")[1]
    assert spread.index("Macro F1 QALD") < spread.index("Intent-based match")
