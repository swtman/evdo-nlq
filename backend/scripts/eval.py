"""Eval harness for NL -> SPARQL quality measurement.

WHAT IS AN EVAL HARNESS?
-------------------------
An eval harness is a script that runs your system automatically on a set of
known-good examples ("gold" examples) and measures how often it produces the
correct answer. This is like a test suite, but instead of testing code logic,
it tests whether the LLM produces SPARQL queries that return the right data.

Run this script after changing the prompt, switching LLM providers, or adding
new few-shot examples to find out whether the pipeline got better or worse.

HOW IT WORKS (in one picture)
------------------------------
  prompts/examples.yaml (gold examples)
    │
    ▼
  For each example:
    [1] Feed the NL question to the pipeline  →  generated SPARQL (LLM only, no GraphDB)
    [2] Execute gold SPARQL against GraphDB   →  gold result set
    [3] Execute generated SPARQL (LIMIT stripped) against GraphDB  →  gen result set
    [4] Compare result sets  →  PASS or FAIL
    [5] Secondary: compare query AST structure  →  structural similarity
  │
  ▼
  Markdown report in notes/eval-runs/

METRICS
--------
- Primary metric: result-set match — do both queries return the same data rows?
  This is what users care about: the right answer, regardless of how the query
  was written.
- Secondary metric: AST canonical match — do the queries have the same
  structure after normalising variable names? Useful supplementary evidence,
  but less reliable than result-set match (see _canonicalize_sparql).

GOLD EXECUTION FAILURES
------------------------
If the gold SPARQL itself fails to execute (e.g. GraphDB is temporarily down,
or the gold query has a bug not caught by offline syntax validation), that
example is EXCLUDED from the accuracy count (result_match=None, broken_gold=True).
This is intentional: a broken gold example is an infra or data problem, not a
model failure, and must not make the accuracy score look worse than it really is.

COMPARISON SEMANTICS
---------------------
Result-set values are compared POSITIONALLY — in the SELECT column order each
query declares — not by column name. A gold query using ?title and a generated
query using ?t are compared first-column-to-first-column. Different variable
names are tolerated; wrong column ordering is not.

Usage (from backend/):
    uv run python scripts/eval.py --prompt-version 1 --provider fake --language english
    uv run python scripts/eval.py --prompt-version 2 --provider claude --model claude-haiku-4-5 --language both

Options:
    --prompt-version  1 or 2 (default: 2)
    --provider        claude | gemini | fake (default: claude)
    --model           model name (default: claude-haiku-4-5)
    --language        greek | english | both (default: both)
    --output          path for the Markdown report (auto-named if omitted)
    --no-skip-eval    include skip_eval: true examples (excluded by default)
    --no-cache        bypass DiskCache for a fresh-LLM eval run
    --example-id      run only this example ID (e.g. ex-005)
    --shape           run only examples with this query_shape (e.g. negative-existence)

Outputs a Markdown report to notes/eval-runs/<auto-named>.md (or --output PATH).
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

# Allow running from backend/ with: uv run python scripts/eval.py
sys.path.insert(0, str(Path(__file__).parent.parent))

import yaml

from app.config import settings
from app.llm.factory import get_provider
from app.ontology.loader import load_summary
from app.pipeline.query_pipeline import (
    PipelineResult,
    QueryPipeline,
    _is_not_answerable,  # shared with production pipeline to guarantee identical detection logic
)
from app.prompts.examples_loader import select_few_shot
from app.prompts.loader import fill, load
from app.sparql.client import SparqlClient, SparqlResult, validate_sparql

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("eval")

_REPO_ROOT = Path(__file__).parent.parent.parent
_EXAMPLES_PATH = _REPO_ROOT / "prompts" / "examples.yaml"
_EVAL_RUNS_DIR = _REPO_ROOT / "notes" / "eval-runs"

# Exhaustive list of accepted comparison_mode values in examples.yaml.
# Validated at startup so a typo is caught before any LLM calls are made.
_KNOWN_COMPARISON_MODES = {"set", "ordered", "scalar", "not-answerable"}


# ---------------------------------------------------------------------------
# AST canonicalization (secondary metric — best-effort only)
# ---------------------------------------------------------------------------


def _canonicalize_sparql(query: str) -> str | None:
    """Parse a SPARQL query into a canonical string form for structural comparison.

    WHAT IS AST CANONICALIZATION?
    ------------------------------
    An Abstract Syntax Tree (AST) is a tree representation of a program's
    structure, stripped of surface details like whitespace and comments.
    Two SPARQL queries with different variable names or formatting can share
    the same AST if they express the same logical graph pattern.

    Canonicalization means transforming that tree into a consistent string so
    that two structurally equivalent queries produce the same string and can
    be compared with a plain equality check.

    WHY DO WE DO IT?
    ----------------
    The LLM might write ?book where the gold query uses ?b, or ?result where
    gold uses ?title. These are superficial differences. Without canonicalization,
    a string comparison would flag them as mismatches even though the queries
    return identical data.

    HOW VARIABLE NORMALIZATION WORKS
    ---------------------------------
    1. rdflib's parseQuery() parses the SPARQL into an internal parse tree.
    2. str(tree) converts that tree to a string representation.
    3. re.sub() walks the string and replaces every SPARQL variable (?someVar)
       with a positional alias ?v0, ?v1, ?v2, ... in the order they first appear.

    For example:
        Gold:      SELECT ?title WHERE { ?book :hasTitle ?title }
        Generated: SELECT ?t    WHERE { ?b    :hasTitle ?t    }
        Both become: SELECT ?v0 WHERE { ?v1 :hasTitle ?v0 }

    IMPORTANT LIMITATIONS — READ THIS BEFORE CITING THE AST METRIC
    ----------------------------------------------------------------
    - rdflib's str(ParseResults) is an INTERNAL implementation detail —
      its output format is not documented or guaranteed to be stable across
      rdflib versions. Two machines running different rdflib versions could
      produce different canonical strings for the same query.
    - The regex ?(\w+) runs on the repr string, which may contain variable-like
      patterns inside string literals or comments. Those would be incorrectly
      renamed, though this is unlikely with typical SPARQL.
    - "First appearance" order means two queries with the same pattern but
      different triple ordering canonicalize to different strings, causing
      false negatives (reporting a mismatch on identical queries).

    Use AST match as a supplementary signal only. Result-set match is the
    ground truth.

    Parameters
    ----------
    query : str
        A raw SPARQL query string (without markdown fences).

    Returns
    -------
    str | None
        Normalized canonical string, or None if rdflib could not parse the
        query. Callers must handle None explicitly (None == None is True, so
        two unparseable queries would compare as matching — guard against this
        by checking for None before comparing).
    """
    from rdflib.plugins.sparql.parser import parseQuery

    try:
        tree = parseQuery(query)
    except Exception:
        return None

    tree_str = str(tree)
    seen: dict[str, str] = {}
    counter = 0

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


def _row_values(row: dict[str, Any], columns: list[str]) -> tuple:
    """Extract a row's values in SELECT-declaration order as a plain tuple.

    WHAT IS "POSITIONAL" ORDERING AND WHY DOES IT MATTER?
    -------------------------------------------------------
    SPARQL SELECT results carry column names (variables like ?title, ?count).
    When comparing a gold query to a generated query, the two may use different
    variable names but produce equivalent data. For example:

        Gold query SELECT:  SELECT ?title ?author
        Gen  query SELECT:  SELECT ?t ?a
        Same data:          ("Algorithms", "Knuth") in both cases

    If we compared by column NAME, every row would fail because "title" != "t".
    Instead, we compare by POSITION: first column of gold against first column
    of generated, second against second, and so on.

    The `columns` parameter comes from SparqlResult.columns, which preserves
    the original SELECT declaration order from the SPARQL query — not
    alphabetical order, not GraphDB's internal order.

    WHY DOES None BECOME ''?
    ------------------------
    In SPARQL, a variable can be "unbound" in a particular row — for example,
    OPTIONAL { ?x :isbn ?isbn } leaves ?isbn absent for books without an ISBN.
    SparqlClient returns that absence as Python None (not the string "None").

    Python 3's sorted() raises TypeError when comparing None to a string:
        sorted([None, "Aristotle"])  →  TypeError

    Replacing None with '' makes every value a string so sorting is safe.
    Both gold and generated results get the same treatment, so the comparison
    is still fair — a None in gold matches a None in generated (both become '').

    Parameters
    ----------
    row : dict[str, Any]
        A single result row as returned by SparqlClient (column name -> value).
    columns : list[str]
        Column names in the order they appear in the SELECT clause.

    Returns
    -------
    tuple
        Values in declaration order, with None replaced by ''.
    """
    return tuple("" if row.get(col) is None else row[col] for col in columns)


def _rows_to_multiset(result: SparqlResult) -> list[tuple]:
    """Convert all result rows to a sorted list of value tuples.

    WHAT IS A MULTISET?
    --------------------
    A set contains each unique element exactly once (no duplicates).
    A multiset (also called a "bag") allows duplicates but has no meaningful
    order — it is like a list where only the counts matter, not the sequence.

    SPARQL SELECT results are semantically multisets: duplicate rows are
    allowed, but row ORDER is not guaranteed (unless you add ORDER BY). To
    compare two multisets for equality, we sort them both: if the sorted lists
    are equal, the multisets are equal regardless of the original row order.

    WHY SORT RATHER THAN USE A frozenset?
    --------------------------------------
    frozenset would deduplicate rows, treating {A, A, B} == {A, B}. We want
    multiset semantics: {A, A, B} != {A, B} because duplicate rows are
    meaningful in a query result. Sorting a list preserves duplicates while
    making the order deterministic for comparison.

    NOTE: This function is used only for comparison_mode == 'set'. The
    'ordered' mode uses the raw, unsorted row list directly in _compare_results.

    Parameters
    ----------
    result : SparqlResult
        The full result object returned by SparqlClient.execute().

    Returns
    -------
    list[tuple]
        Sorted list of per-row value tuples; equal if and only if both result
        sets contain the same rows with the same multiplicities.
    """
    return sorted(_row_values(r, result.columns) for r in result.rows)


def _strip_limit(sparql: str) -> str:
    """Remove only the outermost trailing LIMIT/OFFSET from a SPARQL query.

    WHY STRIP LIMIT AT ALL?
    ------------------------
    The production pipeline appends LIMIT 20 (or similar) so the UI never
    renders hundreds of rows. During eval, we need the FULL result set to
    compare against the gold query, which has no LIMIT. If we kept the LIMIT,
    a correct query returning 100 rows would only execute against 20, and the
    comparison would fail even though the query was right.

    WHY NOT JUST REMOVE ALL LIMIT OCCURRENCES?
    -------------------------------------------
    SPARQL supports subqueries, and LIMIT inside a subquery is semantically
    meaningful. A common pattern for "find the single item with the highest
    count" is:

        SELECT ?book WHERE {
          { SELECT ?book ORDER BY DESC(?count) LIMIT 1 }
        }

    Here the LIMIT 1 is inside the curly braces of the inner SELECT. Removing
    it would change the subquery from "top 1" to "all", producing wrong results.

    HOW THE ANCHORED REGEX STAYS SAFE
    -----------------------------------
    Both regexes are anchored to the END OF THE STRING with the $ metacharacter:

        r"\\bLIMIT\\s+\\d+\\s*$"

    This matches LIMIT only when it appears as the very last content in the
    outer query. Any LIMIT appearing inside a subquery (followed by more
    characters — whitespace, braces, other clauses) will NOT match.

    OFFSET is stripped first because SPARQL syntax places OFFSET after LIMIT
    (e.g. LIMIT 10 OFFSET 5). Stripping OFFSET first ensures we don't leave
    a dangling OFFSET after the LIMIT is removed.

    Parameters
    ----------
    sparql : str
        The generated SPARQL query string (may contain LIMIT/OFFSET).

    Returns
    -------
    str
        The query with the trailing outermost LIMIT and OFFSET removed;
        unchanged if neither is present at the end.
    """
    # Strip trailing OFFSET first (OFFSET always follows LIMIT in valid SPARQL).
    sparql = re.sub(r"\bOFFSET\s+\d+\s*$", "", sparql.strip(), flags=re.IGNORECASE)
    # Then strip trailing LIMIT.
    sparql = re.sub(r"\bLIMIT\s+\d+\s*$", "", sparql.strip(), flags=re.IGNORECASE)
    return sparql.strip()


def _compare_results(gold: SparqlResult, gen: SparqlResult, mode: str) -> bool:
    """Return True if the generated result set matches the gold result set.

    HOW TO CHOOSE A comparison_mode FOR examples.yaml
    ---------------------------------------------------
    The comparison_mode field in each gold example tells this function what
    kind of equality to check. Choose the mode that matches the semantics of
    the gold SPARQL query:

    "set" — unordered multiset comparison (most common mode).
        Use when the query has no ORDER BY, or when row order is irrelevant.
        Both result sets are sorted before comparison, so row order differences
        are ignored. Duplicate rows must still match.

        Example: "List all books by Aristotle."
          Gold returns:  [("Nicomachean Ethics",), ("Politics",)]
          Gen  returns:  [("Politics",), ("Nicomachean Ethics",)]
          → PASS (same rows, different order — doesn't matter)

    "ordered" — strict row-order comparison.
        Use when the query uses ORDER BY and the order is semantically
        meaningful (e.g. a top-N ranking). Both the VALUES and the ROW ORDER
        must match.

        Example: "List the 3 most-enrolled courses, descending."
          Gold returns: [("CS101", 500), ("MATH201", 400), ("PHY301", 300)]
          Gen  returns: [("CS101", 500), ("PHY301", 300), ("MATH201", 400)]
          → FAIL (same rows, wrong order)

    "scalar" — single-row, single-or-multi-column comparison.
        Use when the query returns exactly one row (e.g. a COUNT, an average,
        or a single-value lookup). If either result has 0 or 2+ rows, returns
        False immediately — a scalar query that returns multiple rows is wrong
        regardless of the values.

        Example: "How many textbooks are in the database?"
          Gold returns: [("42",)]
          Gen  returns: [("42",)]
          → PASS

        Example: "How many textbooks...?"
          Gen  returns: []       (model produced a broken query)
          → FAIL (0 rows, expected 1)

    "not-answerable" — handled BEFORE this function is called.
        This mode is intercepted in _eval_example and never reaches here.
        Included in _KNOWN_COMPARISON_MODES for startup validation only.

    POSITIONAL COMPARISON (important — read this)
    ----------------------------------------------
    Values are extracted in each result's own SELECT column order (not
    alphabetical by name). This means a gold query using ?Universities and
    a generated query using ?numUniversities are compared first-column-to-
    first-column. Different variable names are tolerated; swapped column ORDER
    is treated as a failure — if the LLM puts ?departments before ?universities
    when gold has them in the opposite order, the comparison fails even though
    the same data is present.

    This is intentional: for scalar and multi-column results, column position
    carries semantic meaning (e.g. the first column is always the university
    name, the second is always the count).

    Parameters
    ----------
    gold : SparqlResult
        The result of executing the gold SPARQL against GraphDB.
    gen : SparqlResult
        The result of executing the generated (LIMIT-stripped) SPARQL.
    mode : str
        One of "set", "ordered", "scalar". Raises ValueError for anything else
        (startup validation in main() should have caught typos already).

    Returns
    -------
    bool
        True if the result sets match according to the chosen mode.

    Raises
    ------
    ValueError
        If mode is not a known value. Should not fire during normal runs
        because main() validates all modes at startup.
    """
    if mode == "set":
        return _rows_to_multiset(gold) == _rows_to_multiset(gen)
    if mode == "ordered":
        # Row order matters here — do NOT sort.
        return (
            [_row_values(r, gold.columns) for r in gold.rows]
            == [_row_values(r, gen.columns) for r in gen.rows]
        )
    if mode == "scalar":
        # Both results must have exactly one row; positional comparison within it.
        if len(gold.rows) != 1 or len(gen.rows) != 1:
            return False
        return _row_values(gold.rows[0], gold.columns) == _row_values(gen.rows[0], gen.columns)
    raise ValueError(f"Unknown comparison_mode: {mode!r}")


# ---------------------------------------------------------------------------
# Per-example eval
# ---------------------------------------------------------------------------


def _eval_example(
    ex: dict[str, Any],
    pipeline: QueryPipeline,
    sparql_client: SparqlClient,
    language: str,
) -> dict[str, Any]:
    """Run one gold example through the full eval cycle and return a result record.

    WHAT HAPPENS IN THIS FUNCTION (four phases)
    --------------------------------------------
    For every non-NOT_ANSWERABLE example, the eval cycle runs four phases:

    [1] LLM GENERATION — pipeline.run(question) calls the LLM and returns
        the generated SPARQL. The pipeline is a _FixedSystemPipeline subclass
        that SKIPS GraphDB execution — it only calls the LLM. This is
        intentional: the eval harness needs to execute the query itself (with
        LIMIT stripped and with proper error handling for gold failures).

    [2] GOLD EXECUTION — the gold query from examples.yaml is executed against
        GraphDB to get the reference result set. If this fails (network error,
        broken gold query, GraphDB timeout), the example is EXCLUDED from
        metrics rather than counted as a model failure:
            result_match = None   (not False — excluded, not penalised)
            broken_gold = True    (flagged separately in the report)

    [3] GENERATED EXECUTION — the LLM's query is executed with its trailing
        LIMIT/OFFSET stripped (see _strip_limit) so we compare the full result
        set, not a page of 20 rows.

    [4] COMPARISON — _compare_results() checks whether the two result sets
        match according to this example's comparison_mode.

    WHY IS BROKEN GOLD EXCLUDED (result_match=None) INSTEAD OF FAILED (False)?
    ---------------------------------------------------------------------------
    If GraphDB is down or a gold query has a semantic bug that rdflib's offline
    validator missed, executing it raises an exception. This is an infrastructure
    or data quality problem — it tells us nothing about whether the model
    produced good SPARQL. Counting it as a model failure would make accuracy
    look lower than it really is.

    result_match=None is the signal to _render_report to exclude this example
    from the pass/total denominator entirely. The broken_gold=True flag causes
    the report to list it separately with a warning.

    NOT_ANSWERABLE PATH (handled at the top, before the four phases)
    ----------------------------------------------------------------
    When comparison_mode == "not-answerable", the gold answer is a comment
    (# NOT_ANSWERABLE: ...), not executable SPARQL. GraphDB is never called.
    The eval simply checks whether the pipeline also returned a NOT_ANSWERABLE
    comment. If yes → PASS, if no → FAIL.

    The check uses _is_not_answerable() imported directly from query_pipeline.py
    so that the eval and production pipeline use the exact same detection logic
    (same regex, same case-insensitivity). If the detection logic ever changes
    in the pipeline, the eval automatically picks up the change.

    RESULT RECORD FIELDS
    --------------------
    id               : example ID (e.g. "ex-005")
    query_shape      : shape category (e.g. "simple-lookup", "aggregation")
    language         : "greek" or "english"
    question         : the NL question sent to the LLM
    gold_sparql      : the reference SPARQL from examples.yaml
    generated_sparql : what the LLM produced (None if the pipeline errored)
    result_match     : True (PASS) | False (FAIL) | None (SKIP / broken gold)
    ast_match        : True | False | None (not applicable or parse failed)
    error            : human-readable description of any exception
    broken_gold      : True if the gold query itself failed to execute
    input_tokens     : LLM prompt tokens consumed
    output_tokens    : LLM response tokens generated
    duration_s       : wall-clock seconds for this entire example
    """
    question = ex["question_greek"] if language == "greek" else ex["question_english"]
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
        "broken_gold": False,
        "input_tokens": 0,
        "output_tokens": 0,
        "duration_s": 0.0,
    }

    t0 = time.perf_counter()

    # ── NOT_ANSWERABLE path ───────────────────────────────────────────────────
    # The gold is a comment, not SPARQL — no GraphDB calls. Just check whether
    # the LLM also returned a NOT_ANSWERABLE comment.
    if mode == "not-answerable":
        try:
            pr = pipeline.run(question)
            is_na = _is_not_answerable(pr.sparql)
            result["generated_sparql"] = pr.sparql
            result["result_match"] = is_na
            result["ast_match"] = None  # AST comparison makes no sense for a comment
            result["input_tokens"] = pr.input_tokens
            result["output_tokens"] = pr.output_tokens
        except Exception as exc:
            result["error"] = str(exc)
            result["result_match"] = False
        result["duration_s"] = round(time.perf_counter() - t0, 2)
        return result

    # ── Phase 1: LLM generation ───────────────────────────────────────────────
    # The pipeline's _FixedSystemPipeline.run() calls the LLM and returns only
    # the generated SPARQL — GraphDB execution is intentionally skipped there.
    try:
        pr = pipeline.run(question)
        result["generated_sparql"] = pr.sparql
        result["input_tokens"] = pr.input_tokens
        result["output_tokens"] = pr.output_tokens
    except Exception as exc:
        result["error"] = f"Pipeline error: {exc}"
        result["result_match"] = False
        result["ast_match"] = False
        result["duration_s"] = round(time.perf_counter() - t0, 2)
        return result

    # ── Phase 2: execute gold SPARQL ─────────────────────────────────────────
    # A failure here is an infra/gold-data problem, NOT a model failure.
    # We exclude this example from metrics (result_match=None) rather than
    # marking it as a model error (result_match=False).
    try:
        gold_result: SparqlResult = sparql_client.execute(gold_sparql)
    except Exception as exc:
        result["error"] = f"Gold SPARQL execution error: {exc}"
        result["result_match"] = None   # excluded — not the model's fault
        result["broken_gold"] = True
        result["duration_s"] = round(time.perf_counter() - t0, 2)
        return result

    # ── Phase 3: execute generated SPARQL (LIMIT stripped) ───────────────────
    # Strip only the outermost trailing LIMIT so we compare the full result set.
    # LIMIT inside subqueries is preserved by the anchored regex in _strip_limit.
    try:
        gen_result: SparqlResult = sparql_client.execute(_strip_limit(pr.sparql))
    except Exception as exc:
        result["error"] = f"Generated SPARQL execution error: {exc}"
        result["result_match"] = False
        result["ast_match"] = None
        result["duration_s"] = round(time.perf_counter() - t0, 2)
        return result

    # ── Phase 4: compare ─────────────────────────────────────────────────────
    result["result_match"] = _compare_results(gold_result, gen_result, mode)
    result["ast_match"] = _canonicalize_sparql(gold_sparql) == _canonicalize_sparql(pr.sparql)
    result["duration_s"] = round(time.perf_counter() - t0, 2)
    return result


# ---------------------------------------------------------------------------
# Provenance helpers
# ---------------------------------------------------------------------------


def _git_sha() -> str:
    """Return the short git commit hash of HEAD, or 'unknown' if unavailable.

    WHY RECORD THIS IN EVERY EVAL REPORT?
    ----------------------------------------
    Eval results are only meaningful in context. If you run the harness twice
    on different days and get different scores, you need to know: was it a
    different prompt? Different few-shot examples? A bug fix in the pipeline?

    Recording the git SHA answers the "what changed in the code?" question.
    A reader can open a report, see the SHA, check out that exact commit, and
    reproduce the run — or diff it against a newer SHA to see what changed.

    The "short" SHA (7 hex characters) uniquely identifies a commit in a
    repository of this size and is more readable than the full 40-character hash.

    Returns 'unknown' rather than raising an exception so that a missing git
    installation does not crash the eval harness (e.g. in a CI environment
    without a git binary).
    """
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=_REPO_ROOT,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
    except Exception:
        return "unknown"


def _file_sha256(path: Path) -> str:
    """Return the first 12 hex characters of a file's SHA-256 hash.

    WHY HASH PROMPT FILES?
    -----------------------
    Two eval runs can share the same git SHA but use different prompt content
    if the prompt file was modified without being committed (common during
    active development on a feature branch). The file hash captures the ACTUAL
    content used, regardless of git status.

    We hash both the active prompt template (nl-to-sparql-vN.md) and the
    gold example bank (examples.yaml) so the report records exactly which
    inputs produced the measured accuracy score.

    WHY ONLY 12 CHARACTERS?
    ------------------------
    SHA-256 produces a 64-character hex string. A collision between two
    different files requires roughly 2^(12*4/2) ≈ 2^24 ≈ 16 million files.
    For a handful of prompt files, 12 characters is more than sufficient and
    keeps the report table readable.

    Returns 'missing' instead of raising if the file does not exist — this
    can happen if a prompt version is not yet written or the path is wrong.
    """
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    except Exception:
        return "missing"


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
    git_sha: str,
    prompt_sha: str,
    examples_sha: str,
) -> str:
    """Render the full Markdown eval report from per-example result records.

    The report has four sections:
      1. Provenance — git SHA, file hashes, run timestamp.
      2. Summary — overall accuracy, AST accuracy, cost, broken-gold count.
      3. Per-shape accuracy — table breaking down pass/fail by query category.
      4. Per-example results — one subsection per example with SPARQL details.

    EVALABLE vs BROKEN GOLD
    -------------------------
    `evalable` is the subset of results where result_match is not None — i.e.
    examples that completed without a broken gold or other exclusion. Accuracy
    is computed over this subset only (not over all examples). This way, a
    broken gold does not make the accuracy look artificially lower.

    STATUS SYMBOLS
    ---------------
    PASS : result_match is True
    FAIL : result_match is False
    SKIP : result_match is None (broken gold or other exclusion)
    """
    evalable = [r for r in results if r.get("result_match") is not None]
    passed = [r for r in evalable if r["result_match"] is True]
    broken_gold = [r for r in results if r.get("broken_gold")]
    total = len(evalable)
    accuracy = len(passed) / total if total else 0.0

    ast_evalable = [r for r in evalable if r.get("ast_match") is not None]
    ast_passed = [r for r in ast_evalable if r["ast_match"] is True]
    ast_accuracy = len(ast_passed) / len(ast_evalable) if ast_evalable else 0.0

    total_input = sum(r.get("input_tokens", 0) for r in results)
    total_output = sum(r.get("output_tokens", 0) for r in results)
    total_time = sum(r.get("duration_s", 0.0) for r in results)

    # Per-shape breakdown counts only evalable examples.
    shape_stats: dict[str, dict[str, int]] = {}
    for r in evalable:
        s = r["query_shape"]
        if s not in shape_stats:
            shape_stats[s] = {"pass": 0, "total": 0}
        shape_stats[s]["total"] += 1
        if r["result_match"] is True:
            shape_stats[s]["pass"] += 1

    lines = [
        f"# Eval Report — prompt v{prompt_version} | {provider}/{model} | {language} | {run_at}",
        "",
        "## Provenance",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| git HEAD | `{git_sha}` |",
        f"| nl-to-sparql-v{prompt_version}.md sha256[:12] | `{prompt_sha}` |",
        f"| examples.yaml sha256[:12] | `{examples_sha}` |",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Result-set match (primary) | **{len(passed)}/{total} = {accuracy:.0%}** |",
        f"| AST canonical match (secondary) | {len(ast_passed)}/{len(ast_evalable)} = {ast_accuracy:.0%} |",
        f"| Broken-gold excluded | {len(broken_gold)} |",
        f"| Total input tokens | {total_input} |",
        f"| Total output tokens | {total_output} |",
        f"| Total wall time (s) | {total_time:.1f} |",
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
        rm = r.get("result_match")
        if rm is True:
            status = "PASS"
        elif rm is False:
            status = "FAIL"
        else:
            status = "SKIP"
        lines.append(f"### [{status}] {r['id']} — {r['query_shape']}")
        lines.append(f"**Q ({r['language']}):** {r['question']}")
        if r.get("broken_gold"):
            lines.append(
                "**Warning: Gold SPARQL failed to execute — excluded from metrics "
                "(infra/gold issue, not a model failure).**"
            )
        if r.get("error"):
            lines.append(f"**Error:** `{r['error']}`")
        toks = f"tokens: {r.get('input_tokens', 0)}in/{r.get('output_tokens', 0)}out"
        lines.append(
            f"**Result match:** {rm} | **AST match:** {r.get('ast_match')} | "
            f"**Time:** {r.get('duration_s', 0):.1f}s | {toks}"
        )
        # Show gold SPARQL on failures so the reader can spot the difference.
        if r.get("gold_sparql") and rm is False:
            gold = r["gold_sparql"].strip()
            lines.append(
                f"<details><summary>Gold SPARQL</summary>\n\n```sparql\n{gold}\n```\n</details>"
            )
        if r.get("generated_sparql"):
            gen = r["generated_sparql"].strip()
            lines.append(
                f"<details><summary>Generated SPARQL</summary>\n\n```sparql\n{gen}\n```\n</details>"
            )
        lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Pipeline construction
# ---------------------------------------------------------------------------


def _build_pipeline(prompt_version: int, provider_name: str, model: str) -> QueryPipeline:
    """Construct a pipeline that generates SPARQL but SKIPS GraphDB execution.

    WHY SKIP GRAPHDB INSIDE THE PIPELINE?
    ----------------------------------------
    The normal QueryPipeline.run() does three things:
      [1] Generate SPARQL with the LLM
      [2] Validate with rdflib (offline)
      [3] Execute against GraphDB and return results

    The eval harness needs to own step [3] itself because:
      a) It must strip LIMIT before executing the generated query.
      b) It must execute BOTH the gold and generated queries separately.
      c) It must handle gold execution failures as infrastructure issues (not
         model failures), which requires controlling the error path.

    If the pipeline ran step [3] internally, the generated query would be
    executed TWICE — once inside the pipeline (with LIMIT 20) and once in the
    eval (with LIMIT stripped). The inner execution would also return results
    that the eval immediately discards, wasting two GraphDB round-trips.

    Solution: override run() to stop after SPARQL generation and return an
    empty PipelineResult. The eval harness handles GraphDB from there.

    WHY A LOCAL SUBCLASS DEFINED INSIDE THIS FUNCTION?
    ---------------------------------------------------
    Python functions can define classes inside themselves. The inner class
    _FixedSystemPipeline captures the `system` variable from this function's
    local scope via "closure" — a mechanism where an inner function or class
    remembers variables from the scope where it was defined, even after that
    outer function has returned.

    This is the cleanest way to pass the pre-built system prompt into run()
    without adding a constructor parameter or storing it as an instance
    attribute, because:
      1. The system prompt belongs to this specific eval run, not to a
         reusable pipeline class.
      2. The subclass is intentionally not meant for reuse outside eval.py.
      3. Keeping it close to where it is used makes the code easier to read
         without jumping to another module.

    WHY IS THE SYSTEM PROMPT BUILT ONCE (not per question)?
    --------------------------------------------------------
    The system prompt contains the ontology summary (~400 tokens) and, for
    prompt v2, the few-shot examples block. Neither changes across examples
    within the same eval run. Building it once and reusing it:
      - Saves string formatting and file I/O on every example.
      - Guarantees every example in the run sees the exact same prompt.
      - Maximises DiskCache hits: the cache key is sha256(system + user + model).
        Same system + same question = guaranteed cache hit across reruns.

    Parameters
    ----------
    prompt_version : int
        1 or 2 — which prompt template to load from prompts/.
    provider_name : str
        "claude", "gemini", or "fake".
    model : str
        Model identifier string passed to the provider (e.g. "claude-haiku-4-5").

    Returns
    -------
    QueryPipeline
        An instance of _FixedSystemPipeline ready to generate (but not execute) SPARQL.
    """
    provider = get_provider(provider_name, model)
    sparql_client = SparqlClient(settings.graphdb_endpoint)
    ontology = load_summary()

    if prompt_version == 1:
        system = fill(load("nl-to-sparql", 1), ontology_summary=ontology)
    else:
        # v2 adds static few-shot examples via {few_shot_block}.
        # select_few_shot(k=6) picks one example per query_shape, sorted by
        # few_shot_priority, and formats them as a text block for injection.
        system = fill(
            load("nl-to-sparql", prompt_version),
            ontology_summary=ontology,
            few_shot_block=select_few_shot(k=6),
        )

    class _FixedSystemPipeline(QueryPipeline):
        """QueryPipeline subclass that uses a pre-built system prompt and skips GraphDB.

        The parent class's run() builds the system prompt itself and then calls
        _generate_with_retry() followed by SparqlClient.execute(). This override
        ONLY calls _generate_with_retry() and returns an empty PipelineResult.

        GraphDB execution is intentionally omitted here — the eval harness
        (_eval_example) executes both the gold and generated queries in the
        right order with the right error handling.

        The `system` and `ontology` variables are captured from
        _build_pipeline's scope via closure — no extra constructor arguments needed.
        """

        def run(self, question: str) -> PipelineResult:  # type: ignore[override]
            sparql, ti, to, retries = self._generate_with_retry(
                system, question, ontology
            )
            # Return empty columns/rows — the eval harness executes GraphDB itself.
            return PipelineResult(
                sparql=sparql,
                columns=[],
                rows=[],
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


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point: parse arguments, validate inputs, run eval, write report.

    STARTUP VALIDATION — FAIL FAST BEFORE ANY API CALLS
    ----------------------------------------------------
    Two things are validated before any LLM tokens are spent:

    [1] comparison_mode validation — every example's mode must be one of the
        values in _KNOWN_COMPARISON_MODES. A typo like "ste" (instead of "set")
        would silently make every comparison return False without this check.

    [2] Gold SPARQL syntax validation — every non-NOT_ANSWERABLE example's gold
        query is parsed by rdflib's offline validator. If any gold query is
        syntactically broken, the harness exits immediately listing all bad
        examples. This prevents the frustrating scenario where 20 minutes of
        API calls complete successfully and THEN every example fails because
        the gold was wrong all along.

        Note: rdflib catches syntax errors but NOT semantic errors (e.g. a
        class that does not exist in the ontology). Semantic errors only surface
        at runtime as GraphDB execution failures (handled per-example as
        broken_gold).

    FILTER APPLICATION ORDER
    ------------------------
    After loading all examples, filters are applied in this sequence:
      1. skip_eval filter (unless --no-skip-eval): removes work-in-progress
         examples marked skip_eval: true in examples.yaml.
      2. --example-id filter: run a single example for debugging.
      3. --shape filter: run all examples of one query_shape category.

    Applying --example-id and --shape together is allowed but almost always
    returns 0 results (a specific example only belongs to one shape).

    LANGUAGE LOOP AND REPORT STRUCTURE
    -----------------------------------
    With --language both (the default), every example runs TWICE: once with
    question_greek and once with question_english. The results list contains
    one entry per (example, language) pair, so N examples → 2N result records.
    The per-shape accuracy table aggregates both language passes together.
    This lets you spot whether the model performs differently in Greek vs English,
    but note that both runs use the same dual-language few-shot prompt — the
    per-language scores measure question-text differences, not prompt-language
    differences.

    PROVENANCE GATHERING
    --------------------
    After all examples finish, the git SHA and file hashes are collected and
    written into the report header. Collecting provenance at the END (not the
    START) ensures the hashes reflect the actual state of files when the run
    completed — if you edited a prompt mid-run, the hash will reflect the
    edited version.
    """
    parser = argparse.ArgumentParser(description="Eval harness for NL->SPARQL.")
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
        "--no-skip-eval",
        action="store_true",
        default=False,
        help="Include examples marked skip_eval: true (excluded by default)",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        default=False,
        help="Bypass LLM DiskCache -- forces fresh API calls (sets LLM_CACHE_DISABLED=1)",
    )
    parser.add_argument(
        "--example-id",
        default=None,
        metavar="ID",
        help="Run only this example ID (e.g. ex-005)",
    )
    parser.add_argument(
        "--shape",
        default=None,
        metavar="SHAPE",
        help="Run only examples with this query_shape (e.g. negative-existence)",
    )
    args = parser.parse_args()

    # --no-cache bypasses the DiskCache, which normally stores LLM responses on
    # disk keyed by sha256(system + user + model). Bypassing ensures fresh LLM
    # calls for every example — necessary when you want to measure true model
    # performance rather than replaying cached responses from a previous run.
    if args.no_cache:
        os.environ["LLM_CACHE_DISABLED"] = "1"

    # Load all examples from the gold bank.
    raw = yaml.safe_load(_EXAMPLES_PATH.read_text(encoding="utf-8"))
    all_examples: list[dict[str, Any]] = raw.get("examples", [])

    # Validate comparison_mode values before spending any tokens.
    # We check all examples (not just the filtered subset) so that a typo in
    # a skip_eval example is still caught — it would cause a crash if ever run.
    for ex in all_examples:
        mode = ex.get("comparison_mode", "")
        if mode not in _KNOWN_COMPARISON_MODES:
            sys.exit(f"ERROR: example {ex.get('id')} has unknown comparison_mode={mode!r}")

    # Validate gold SPARQL syntax before spending any tokens.
    # rdflib's offline parser is fast (no network) and catches most mistakes.
    # NOT_ANSWERABLE examples are skipped — their "gold" is a comment string
    # (# NOT_ANSWERABLE: ...), not executable SPARQL.
    broken_gold: list[str] = []
    for ex in all_examples:
        if ex.get("comparison_mode") == "not-answerable":
            continue
        err = validate_sparql(ex["gold_sparql"].strip())
        if err:
            broken_gold.append(f"  {ex['id']}: {err[:80]}")
    if broken_gold:
        sys.exit(
            "ERROR: broken gold SPARQL in examples.yaml -- fix before running eval:\n"
            + "\n".join(broken_gold)
        )

    # Apply example filters.
    examples = all_examples
    if not args.no_skip_eval:
        examples = [e for e in examples if not e.get("skip_eval", False)]
    if args.example_id:
        examples = [e for e in examples if e["id"] == args.example_id]
        if not examples:
            sys.exit(f"ERROR: no example with id={args.example_id!r}")
    if args.shape:
        examples = [e for e in examples if e["query_shape"] == args.shape]
        if not examples:
            sys.exit(f"ERROR: no examples with shape={args.shape!r}")

    languages = ["greek", "english"] if args.language == "both" else [args.language]

    run_at = datetime.now().strftime("%Y-%m-%dT%H:%M")
    results: list[dict[str, Any]] = []

    sparql_client = SparqlClient(settings.graphdb_endpoint)
    pipeline = _build_pipeline(args.prompt_version, args.provider, args.model)

    for lang in languages:
        print(
            f"\nRunning eval: prompt=v{args.prompt_version} provider={args.provider} "
            f"model={args.model} lang={lang}"
        )
        for ex in examples:
            print(f"  {ex['id']} ({ex['query_shape']}) ...", end="", flush=True)
            result = _eval_example(ex, pipeline, sparql_client, lang)
            results.append(result)
            rm = result["result_match"]
            sym = "PASS" if rm is True else ("SKIP" if rm is None else "FAIL")
            print(f" {sym} ({result['duration_s']:.1f}s)")

    # Gather provenance metadata after all examples complete.
    # File hashes reflect the content actually used during this run.
    prompt_path = _REPO_ROOT / "prompts" / f"nl-to-sparql-v{args.prompt_version}.md"
    report = _render_report(
        results,
        prompt_version=args.prompt_version,
        provider=args.provider,
        model=args.model,
        language=args.language,
        run_at=run_at,
        git_sha=_git_sha(),
        prompt_sha=_file_sha256(prompt_path),
        examples_sha=_file_sha256(_EXAMPLES_PATH),
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
