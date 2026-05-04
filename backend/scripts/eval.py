"""Eval harness for NL → SPARQL quality measurement.

Runs every gold example from prompts/examples.yaml through the pipeline,
executes both the gold and generated SPARQL against GraphDB, and reports
result-set match (primary) and AST canonical match (secondary).

Usage (from backend/):
    uv run python scripts/eval.py --prompt-version 1 --provider fake --language english
    uv run python scripts/eval.py --prompt-version 2 --provider claude --model claude-haiku-4-5 --language both

Outputs a Markdown report to notes/eval-runs/<auto-named>.md (or --output PATH).
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Allow running from backend/ with: uv run python scripts/eval.py
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

from app.config import settings
from app.llm.factory import get_provider
from app.ontology.loader import load_summary
from app.pipeline.query_pipeline import QueryPipeline
from app.prompts.examples_loader import select_few_shot
from app.prompts.loader import fill, load
from app.sparql.client import SparqlClient, SparqlResult, validate_sparql

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("eval")

_REPO_ROOT = Path(__file__).parent.parent.parent
_EXAMPLES_PATH = _REPO_ROOT / "prompts" / "examples.yaml"
_EVAL_RUNS_DIR = _REPO_ROOT / "notes" / "eval-runs"


# ---------------------------------------------------------------------------
# AST canonicalization (secondary metric)
# ---------------------------------------------------------------------------


def _canonicalize_sparql(query: str) -> str | None:
    """Parse and canonicalize a SPARQL query for structural comparison.

    Returns a normalized string, or None if parsing fails.
    Variable names are replaced with positional aliases (?v0, ?v1, …) by
    first-appearance order so that superficial renaming doesn't cause mismatches.
    """
    from rdflib.plugins.sparql.parser import parseQuery

    try:
        tree = parseQuery(query)
    except Exception:
        return None

    # Collect variable names in order of first appearance in string form.
    tree_str = str(tree)
    seen: dict[str, str] = {}
    counter = 0

    import re

    def replace_var(m: re.Match) -> str:  # type: ignore[type-arg]
        nonlocal counter
        name = m.group(1)
        if name not in seen:
            seen[name] = f"v{counter}"
            counter += 1
        return f"?{seen[name]}"

    return re.sub(r"\?(\w+)", replace_var, tree_str)


# ---------------------------------------------------------------------------
# Result-set comparison
# ---------------------------------------------------------------------------


def _row_values(row: dict[str, Any]) -> tuple:
    """Canonical per-row value tuple: sort by key name so column aliases don't matter."""
    return tuple(v for _, v in sorted(row.items()))


def _rows_to_multiset(rows: list[dict[str, Any]]) -> list[tuple]:
    """Convert result rows to a sorted multiset of value-tuples for comparison.

    Key names (column aliases) are intentionally ignored — two queries that
    return the same data under different column names compare as equal.
    """
    return sorted(_row_values(r) for r in rows)


def _strip_limit(sparql: str) -> str:
    """Remove LIMIT and OFFSET clauses from a SPARQL query for eval execution.

    The LLM adds LIMIT 50 by default; eval needs the full result set to compare
    against gold which has no LIMIT.
    """
    import re
    sparql = re.sub(r"\bLIMIT\s+\d+\b", "", sparql, flags=re.IGNORECASE)
    sparql = re.sub(r"\bOFFSET\s+\d+\b", "", sparql, flags=re.IGNORECASE)
    return sparql.strip()


def _compare_results(
    gold_rows: list[dict[str, Any]],
    gen_rows: list[dict[str, Any]],
    mode: str,
) -> bool:
    """Return True if results match according to comparison_mode.

    Column names (SELECT aliases) are ignored — only values are compared.
    This tolerates the LLM choosing different variable names than the gold query.
    """
    if mode == "set":
        return _rows_to_multiset(gold_rows) == _rows_to_multiset(gen_rows)
    if mode == "ordered":
        # Preserve row order; ignore column names within each row.
        return [_row_values(r) for r in gold_rows] == [_row_values(r) for r in gen_rows]
    if mode == "scalar":
        if len(gold_rows) != 1 or len(gen_rows) != 1:
            return False
        return sorted(gold_rows[0].values()) == sorted(gen_rows[0].values())
    return False  # unknown mode → fail safe


# ---------------------------------------------------------------------------
# Per-example eval
# ---------------------------------------------------------------------------


def _eval_example(
    ex: dict[str, Any],
    pipeline: QueryPipeline,
    sparql_client: SparqlClient,
    language: str,
) -> dict[str, Any]:
    """Run one example through the pipeline and return a result record."""
    question = (
        ex["question_greek"] if language == "greek" else ex["question_english"]
    )
    mode = ex["comparison_mode"]
    gold_sparql: str = ex["gold_sparql"].strip()

    result: dict[str, Any] = {
        "id": ex["id"],
        "query_shape": ex["query_shape"],
        "language": language,
        "question": question,
        "gold_sparql": gold_sparql,
        "generated_sparql": None,
        "result_match": None,
        "ast_match": None,
        "error": None,
    }

    # NOT_ANSWERABLE examples: pass iff pipeline returns a NOT_ANSWERABLE comment.
    if mode == "not-answerable":
        try:
            pr = pipeline.run(question)
            is_na = pr.sparql.strip().startswith("# NOT_ANSWERABLE")
            result["generated_sparql"] = pr.sparql
            result["result_match"] = is_na
            result["ast_match"] = is_na
        except Exception as exc:
            result["error"] = str(exc)
            result["result_match"] = False
            result["ast_match"] = False
        return result

    # Normal examples.
    try:
        pr = pipeline.run(question)
        result["generated_sparql"] = pr.sparql
    except Exception as exc:
        result["error"] = f"Pipeline error: {exc}"
        result["result_match"] = False
        result["ast_match"] = False
        return result

    # Execute gold SPARQL.
    try:
        gold_result: SparqlResult = sparql_client.execute(gold_sparql)
    except Exception as exc:
        result["error"] = f"Gold SPARQL execution error: {exc}"
        result["result_match"] = False
        result["ast_match"] = False
        return result

    # Execute generated SPARQL (strip LIMIT so the full result set is comparable).
    try:
        gen_result: SparqlResult = sparql_client.execute(_strip_limit(pr.sparql))
    except Exception as exc:
        result["error"] = f"Generated SPARQL execution error: {exc}"
        result["result_match"] = False
        result["ast_match"] = None
        return result

    result["result_match"] = _compare_results(gold_result.rows, gen_result.rows, mode)
    result["ast_match"] = _canonicalize_sparql(gold_sparql) == _canonicalize_sparql(
        pr.sparql
    )
    return result


# ---------------------------------------------------------------------------
# Report rendering
# ---------------------------------------------------------------------------


def _render_report(
    results: list[dict[str, Any]],
    prompt_version: int,
    provider: str,
    model: str,
    language: str,
    run_at: str,
) -> str:
    evalable = [r for r in results if r.get("result_match") is not None]
    passed = [r for r in evalable if r["result_match"]]
    total = len(evalable)
    accuracy = len(passed) / total if total else 0.0

    ast_evalable = [r for r in evalable if r.get("ast_match") is not None]
    ast_passed = [r for r in ast_evalable if r["ast_match"]]
    ast_accuracy = len(ast_passed) / len(ast_evalable) if ast_evalable else 0.0

    # Per-shape breakdown.
    shape_stats: dict[str, dict[str, int]] = {}
    for r in evalable:
        s = r["query_shape"]
        if s not in shape_stats:
            shape_stats[s] = {"pass": 0, "total": 0}
        shape_stats[s]["total"] += 1
        if r["result_match"]:
            shape_stats[s]["pass"] += 1

    lines = [
        f"# Eval Report — prompt v{prompt_version} | {provider}/{model} | {language} | {run_at}",
        "",
        "## Summary",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Result-set match (primary) | **{len(passed)}/{total} = {accuracy:.0%}** |",
        f"| AST canonical match (secondary) | {len(ast_passed)}/{len(ast_evalable)} = {ast_accuracy:.0%} |",
        "",
        "## Per-shape accuracy",
        "",
        "| Query shape | Pass | Total | % |",
        "|---|---|---|---|",
    ]
    for shape, st in sorted(shape_stats.items()):
        pct = st["pass"] / st["total"] if st["total"] else 0.0
        lines.append(f"| {shape} | {st['pass']} | {st['total']} | {pct:.0%} |")

    lines += ["", "## Per-example results", ""]
    for r in results:
        status = "✓" if r.get("result_match") else ("–" if r.get("result_match") is None else "✗")
        lines.append(f"### {status} {r['id']} — {r['query_shape']}")
        lines.append(f"**Q ({r['language']}):** {r['question']}")
        if r.get("error"):
            lines.append(f"**Error:** {r['error']}")
        lines.append(f"**Result match:** {r.get('result_match')} | **AST match:** {r.get('ast_match')}")
        if r.get("generated_sparql"):
            gen = r["generated_sparql"].strip()
            lines.append(f"<details><summary>Generated SPARQL</summary>\n\n```sparql\n{gen}\n```\n</details>")
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_pipeline(prompt_version: int, provider_name: str, model: str) -> QueryPipeline:
    """Construct a QueryPipeline with the given settings."""
    provider = get_provider(provider_name, model)
    sparql_client = SparqlClient(settings.graphdb_endpoint)

    # Monkey-patch the pipeline's prompt version via a subclass to avoid
    # modifying query_pipeline.py's default version constant.
    ontology = load_summary()

    if prompt_version == 1:
        system = fill(load("nl-to-sparql", 1), ontology_summary=ontology)
    else:
        system = fill(
            load("nl-to-sparql", prompt_version),
            ontology_summary=ontology,
            few_shot_block=select_few_shot(k=6),
        )

    class _FixedSystemPipeline(QueryPipeline):
        """Pipeline subclass that uses a pre-built system prompt."""

        def run(self, question: str):  # type: ignore[override]
            sparql, ti, to, retries = self._generate_with_retry(
                system, question, ontology
            )
            result = self._sparql_client.execute(sparql)
            from app.pipeline.query_pipeline import PipelineResult

            return PipelineResult(
                sparql=sparql,
                columns=result.columns,
                rows=result.rows,
                provider=self._provider_name,
                model=self._model_name,
                input_tokens=ti,
                output_tokens=to,
                retries=retries,
            )

    return _FixedSystemPipeline(
        provider=provider,
        sparql_client=sparql_client,
        provider_name=provider_name,
        model_name=model,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Eval harness for NL→SPARQL.")
    parser.add_argument("--prompt-version", type=int, default=2, choices=[1, 2])
    parser.add_argument("--provider", default="claude", choices=["claude", "gemini", "fake"])
    parser.add_argument("--model", default="claude-haiku-4-5")
    parser.add_argument(
        "--language",
        default="both",
        choices=["greek", "english", "both"],
    )
    parser.add_argument("--output", default=None, help="Output .md path (auto-named if omitted)")
    parser.add_argument(
        "--skip-eval-flag",
        action="store_true",
        default=True,
        help="Skip examples marked skip_eval: true (default: true)",
    )
    args = parser.parse_args()

    # Load examples.
    raw = yaml.safe_load(_EXAMPLES_PATH.read_text(encoding="utf-8"))
    all_examples: list[dict[str, Any]] = raw.get("examples", [])
    if args.skip_eval_flag:
        examples = [e for e in all_examples if not e.get("skip_eval", False)]
    else:
        examples = all_examples

    languages = ["greek", "english"] if args.language == "both" else [args.language]

    run_at = datetime.now().strftime("%Y-%m-%dT%H:%M")
    results: list[dict[str, Any]] = []

    sparql_client = SparqlClient(settings.graphdb_endpoint)
    pipeline = _build_pipeline(args.prompt_version, args.provider, args.model)

    for lang in languages:
        print(f"\nRunning eval: prompt=v{args.prompt_version} provider={args.provider} model={args.model} lang={lang}")
        for ex in examples:
            ex_id = ex["id"]
            print(f"  {ex_id} ({ex['query_shape']}) ...", end="", flush=True)
            result = _eval_example(ex, pipeline, sparql_client, lang)
            results.append(result)
            sym = "✓" if result["result_match"] else ("–" if result["result_match"] is None else "✗")
            print(f" {sym}")

    report = _render_report(
        results,
        prompt_version=args.prompt_version,
        provider=args.provider,
        model=args.model,
        language=args.language,
        run_at=run_at,
    )

    if args.output:
        out_path = Path(args.output)
    else:
        slug = f"{run_at[:10]}-v{args.prompt_version}-{args.language}-{args.provider}-{args.model}"
        _EVAL_RUNS_DIR.mkdir(parents=True, exist_ok=True)
        out_path = _EVAL_RUNS_DIR / f"{slug}.md"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")
    print(f"\nReport written to: {out_path}")


if __name__ == "__main__":
    main()
