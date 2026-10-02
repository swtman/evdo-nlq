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
    [4] Score the two result sets  →  intent / strict / F1 (+ answer kind, failure cause)
    [5] Secondary: compare query AST structure  →  structural similarity
  │
  ▼
  Markdown report in notes/eval-runs/ (+ a JSON sidecar with every per-item score)

METRICS (ADR-038 — three numbers, never one)
--------------------------------------------
All three are execution-based: the answer is judged, not the query text. The rules live in
app/evaluation/metrics.py (pure functions); interval and test maths in app/evaluation/stats.py.
- Macro F1 QALD — the HEADLINE: per-question precision/recall/F over answer sets with QALD-9's
  empty-answer rules, averaged over items (partial credit for near misses). The established
  metric for question answering over knowledge graphs (QALD-9 ranking; TEXT2SPARQL'25).
- Intent-based match (Floratou et al., CIDR 2024, §4 — a recent proposal for SQL, adapted):
  pass/fail; rows as a true set, gold columns matched to generated columns by content in any
  order, extra generated columns allowed, a "none" accepted as ASK false / empty SELECT / 0.
- Strict execution match — the rule every report used before ADR-038 (positional columns,
  "set" = multiset); kept so old and new numbers stay comparable.
Every rate gets a 95% interval (Wilson; bootstrap for F1). Secondary: AST canonical match —
same structure after normalising variable names (see _canonicalize_sparql).

LEAKAGE: ITEMS SHOWN IN THE PROMPT ARE NOT SCORED (ADR-038)
------------------------------------------------------------
When the evaluated file is the few-shot bank (prompts/examples.yaml) and the prompt has a
{few_shot_block} slot, the examples the prompt shows (examples_loader.few_shot_ids) are listed
in their own report section and left out of the headline numbers — the model has seen their
gold query, so they do not test it. One bridge row keeps "strict over every item", the basis
of the reports written before ADR-038.

REPEATED RUNS AND RE-SCORING
----------------------------
--runs N (needs --no-cache) runs the whole set N times — LLM output varies between runs even at
"deterministic" settings (Atil et al., arXiv:2408.04667) and the DiskCache would hide it — and
writes one report per run plus a summary (mean ± SD, per-item passes k/N).
--rescore REPORT.md calls no LLM: it takes the generated queries from an existing report,
re-executes gold and generated queries, and scores them with today's rules.
Paired comparison of two runs (McNemar, paired bootstrap): scripts/compare_runs.py A.json B.json.

GOLD EXECUTION FAILURES
------------------------
If the gold SPARQL itself fails to execute (e.g. GraphDB is temporarily down,
or the gold query has a bug not caught by offline syntax validation), that
example is EXCLUDED from the accuracy count (result_match=None, broken_gold=True).
This is intentional: a broken gold example is an infra or data problem, not a
model failure, and must not make the accuracy score look worse than it really is.

COMPARISON SEMANTICS
---------------------
Column NAMES never matter (?title vs ?t). The strict metric compares columns POSITIONALLY —
in the SELECT order each query declares — so a swapped column order fails it; the intent and
F1 metrics match columns by CONTENT instead, so it does not (app/evaluation/metrics.py).

GREEK ONLY (ADR-033)
---------------------
Users ask in Greek (a question may contain English words), so every example runs once, with
its question_greek; the gold files carry no English translation. Reports keep the word
"greek" in the header and file name so they line up with the earlier `-greek-` runs.

Usage (from backend/):
    uv run python scripts/eval.py --provider claude --model claude-haiku-4-5
    uv run python scripts/eval.py --prompt-version 1 --provider fake

Options:
    --prompt-version  any prompts/nl-to-sparql-v<N>.md on disk (default: PROMPT_VERSION from
                      app/pipeline/query_pipeline.py — the production prompt). Grounded
                      versions are built per question by production's _build_prompt (ADR-025/026).
    --examples-file   gold example file (default: prompts/examples.yaml)
    --provider        claude | gemini | fake (default: claude)
    --model           model name (default: claude-haiku-4-5)
    --output          path for the Markdown report (auto-named if omitted)
    --no-skip-eval    include skip_eval: true examples (excluded by default)
    --no-cache        bypass DiskCache for a fresh-LLM eval run
    --example-id      run only this example ID (e.g. ex-005)
    --shape           run only examples with this query_shape (e.g. negative-existence)
    --split           dev | test — only items of that split (eval-titles.yaml); items without a
                      split always run (ADR-034)
    --runs N          run the set N times (N > 1 needs --no-cache); one report per run + summary
    --rescore REPORT  score the generated queries of an existing report again — no LLM call;
                      the examples file and prompt version are read from the report

Outputs a Markdown report to notes/eval-runs/<auto-named>.md (or --output PATH) and, next to
it, a .json sidecar with every per-item score (the input of scripts/compare_runs.py).
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import logging
import os
import re
import statistics
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
from app.evaluation.metrics import (
    NOT_ANSWERABLE,
    answer_kind,
    f1_qald,
    failure_cause,
    intent_match,
    strict_match,
)
from app.evaluation.metrics import row_values as _row_values  # noqa: F401 — old name (S47/S49)
from app.evaluation.metrics import rows_to_multiset as _rows_to_multiset  # noqa: F401 — old name
from app.evaluation.stats import bootstrap_ci, wilson
from app.grounding import db as grounding_db
from app.llm.factory import get_provider
from app.ontology.loader import load_summary
from app.pipeline.query_pipeline import (
    FEW_SHOT_K,
    PROMPT_VERSION,
    PipelineResult,
    QueryPipeline,
    _is_not_answerable,  # shared with production pipeline to guarantee identical detection logic
)
from app.prompts.examples_loader import few_shot_ids, select_few_shot
from app.prompts.loader import fill, load, load_user_template
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
    - The regex ?(\\w+) runs on the repr string, which may contain variable-like
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


# The row helpers and the strict rule moved to app/evaluation/metrics.py (ADR-038). They are
# imported above under their old private names (_row_values, _rows_to_multiset) and
# _compare_results stays below as a thin alias, because the evidence scripts (S47, S49) and the
# tests load this module and call them by those names.


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
    """The STRICT metric (``app.evaluation.metrics.strict_match``), under its old name.

    HOW TO CHOOSE A comparison_mode FOR A GOLD FILE
    -----------------------------------------------
    "set"     — row order is irrelevant (most items). Strict compares a multiset (duplicates
                count); intent and F1 compare true sets.
    "ordered" — the question asks for an order (ORDER BY, top-N): rows must come in the gold's
                order (strict: every row; intent: the distinct rows).
    "scalar"  — the answer is ONE row (a COUNT, a single lookup); 0 or 2+ rows fail. A gold
                COUNT of 0 is read as a "no" by the intent and F1 metrics (answer kind
                "zero-or-no", ADR-038) — no extra field is needed in the (frozen) gold files.
    "not-answerable" — decided before scoring (``_score_generated``); never reaches here.

    Raises ``ValueError`` for an unknown mode (main() validates every mode at startup).
    """
    return strict_match(gold, gen, mode)


# ---------------------------------------------------------------------------
# Per-example eval
# ---------------------------------------------------------------------------


def _new_record(ex: dict[str, Any]) -> dict[str, Any]:
    """An unscored result record for one gold item (fields: see ``_eval_example``)."""
    return {
        "id": ex["id"],
        "query_shape": ex["query_shape"],
        "question": ex["question_greek"],
        "gold_sparql": ex["gold_sparql"].strip(),
        "generated_sparql": None,
        "result_match": None,
        "intent_match": None,
        "precision": None,
        "recall": None,
        "f1": None,
        "answer_kind": None,
        "cause": None,
        "shown": False,
        "title_offered": None,
        "ast_match": None,
        "error": None,
        "broken_gold": False,
        "input_tokens": 0,
        "output_tokens": 0,
        "duration_s": 0.0,
    }


def _eval_example(
    ex: dict[str, Any],
    pipeline: QueryPipeline,
    sparql_client: SparqlClient,
) -> dict[str, Any]:
    """Run one gold example (its Greek question) through the eval cycle; return a result record.

    WHAT HAPPENS IN THIS FUNCTION
    -----------------------------
    [1] LLM GENERATION — pipeline.run(question) calls the LLM and returns the generated SPARQL
        (the _GenerateOnlyPipeline skips GraphDB; this harness executes the queries itself).
        For an item that names titles (``expected_titles``) the grounding block the prompt
        carried is checked too: did it offer every expected title? (``title_offered``)
    [2]–[4] EXECUTE AND SCORE — ``_score_generated``, shared with --rescore: the gold query,
        then the generated one (trailing LIMIT stripped), then the three metrics.

    WHY IS BROKEN GOLD EXCLUDED (scores None) INSTEAD OF FAILED (False)?
    --------------------------------------------------------------------
    If GraphDB is down or a gold query has a semantic bug that rdflib's offline validator
    missed, the gold cannot be executed. That says nothing about the model, so the item leaves
    the denominator (every score None, ``broken_gold`` True) instead of counting as a failure.

    RESULT RECORD FIELDS
    --------------------
    id, query_shape, question, gold_sparql, generated_sparql (None if the pipeline failed)
    result_match   : STRICT verdict (the pre-ADR-038 rule — the name is kept for continuity)
    intent_match   : intent-based pass/fail verdict (ADR-038)
    precision, recall, f1 : this item's QALD-9 P/R/F (``f1_qald``) — the mean f1 is the headline
    answer_kind    : not-answerable | zero-or-no | count | list (read from the gold result)
    cause          : why the item did not pass every metric (``failure_cause``), else None
    shown          : the prompt shows this item as a worked example (set by _run; not scored)
    title_offered  : grounding offered every expected title (title items only), else None
    ast_match      : True | False | None (not applicable or unparseable)
    error, broken_gold, input_tokens, output_tokens, duration_s
    Scores are None for an excluded item (broken gold).
    """
    record = _new_record(ex)
    t0 = time.perf_counter()
    try:
        pr = pipeline.run(record["question"])
    except Exception as exc:
        record["error"] = f"Pipeline error: {exc}"
        generated = None
    else:
        generated = pr.sparql
        record["generated_sparql"] = pr.sparql
        record["input_tokens"] = pr.input_tokens
        record["output_tokens"] = pr.output_tokens
        record["title_offered"] = _title_offered(ex, getattr(pipeline, "last_user", None))
    _score_generated(ex, generated, sparql_client, record)
    record["duration_s"] = round(time.perf_counter() - t0, 2)
    return record


def _score_generated(
    ex: dict[str, Any],
    generated: str | None,
    sparql_client: SparqlClient,
    record: dict[str, Any],
) -> dict[str, Any]:
    """Execute the gold and the generated query and fill every score of ``record``.

    Shared by live runs (``_eval_example``) and --rescore (``_rescore``), so a re-scored report
    is scored exactly like a fresh one. ``generated`` is None when there is no query (the
    pipeline failed). Order matters:

    - NOT_ANSWERABLE items: no GraphDB call; pass iff the model also said NOT_ANSWERABLE
      (``_is_not_answerable`` is imported from the production pipeline — identical detection).
    - the GOLD runs first: if it fails the item is excluded (see ``_eval_example``).
    - no query, or a NOT_ANSWERABLE comment for an answerable question, or a query GraphDB
      rejects → "no answer": every match False, F1 = (1, 0, 0) per QALD-9 (0 on an empty gold).
    - otherwise the three metrics of app/evaluation/metrics.py, plus the answer kind and the
      failure cause; AST match only when both queries parse.
    """
    mode = ex["comparison_mode"]
    if mode == "not-answerable":
        ok = generated is not None and _is_not_answerable(generated)
        score = 1.0 if ok else 0.0
        record.update(result_match=ok, intent_match=ok, precision=score, recall=score, f1=score)
        record["answer_kind"] = NOT_ANSWERABLE
        if not ok:
            record["cause"] = (
                "pipeline error" if generated is None else "answered a not-answerable question"
            )
        return record

    try:
        gold = sparql_client.execute(record["gold_sparql"])
    except Exception as exc:
        record["error"] = f"Gold SPARQL execution error: {exc}"
        record["broken_gold"] = True
        return record  # every score stays None — excluded, not the model's fault

    gen: SparqlResult | None = None
    failure: str | None = None
    if generated is None:
        failure = "pipeline error"
        record["ast_match"] = False
    elif _is_not_answerable(generated):
        failure = "said not answerable"  # a comment, not a query — never sent to GraphDB
    else:
        try:
            gen = sparql_client.execute(_strip_limit(generated))
        except Exception as exc:
            record["error"] = f"Generated SPARQL execution error: {exc}"
            failure = "execution error"

    strict = gen is not None and strict_match(gold, gen, mode)
    intent = gen is not None and intent_match(gold, gen, mode)
    p, r, f = f1_qald(gold, gen, mode)
    record.update(result_match=strict, intent_match=intent, precision=p, recall=r, f1=f)
    record["answer_kind"] = answer_kind(gold, mode)
    record["cause"] = failure_cause(
        gold, gen, mode, strict=strict, intent=intent, f1=f, error=failure
    )
    if gen is not None and generated is not None:
        gold_ast = _canonicalize_sparql(record["gold_sparql"])
        gen_ast = _canonicalize_sparql(generated)
        # None == None would read two unparseable queries as "the same structure".
        record["ast_match"] = None if gold_ast is None or gen_ast is None else gold_ast == gen_ast
    return record


_CHECK_TITLES_PATH = Path(__file__).with_name("check_titles.py")
_check_titles: Any = None  # scripts/check_titles.py, loaded on first use (scripts/ is no package)


def _title_offered(ex: dict[str, Any], user_message: Any) -> bool | None:
    """Did grounding offer every expected title of a title item? (S44/S47's split.)

    Uses check_titles.score_item(...)["found_all"] on the user message the prompt carried (the
    grounding hints are in it since ADR-026) — the same definition as the S47 analysis ("title
    offered 21 → 28/32"). None for items that name no title, or when no prompt was captured.
    """
    global _check_titles
    if not ex.get("expected_titles") or not isinstance(user_message, str):
        return None
    if _check_titles is None:
        spec = importlib.util.spec_from_file_location("check_titles", _CHECK_TITLES_PATH)
        assert spec is not None and spec.loader is not None
        _check_titles = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_check_titles)
    kind = "two-titles" if len(ex["expected_titles"]) > 1 else "named"
    item = {**ex, "kind": kind, "split": ex.get("split", "")}
    return bool(_check_titles.score_item(item, user_message)["found_all"])


def _rescore(
    examples: list[dict[str, Any]],
    generated: dict[str, str | None],
    sparql_client: SparqlClient,
) -> list[dict[str, Any]]:
    """Score the generated queries of an earlier run again — no LLM call (--rescore, ADR-038).

    ``generated`` maps item id → the query the report recorded (None = the pipeline failed).
    Only items present in the report are scored; nothing is invented for the others. Tokens
    and times stay 0 (they belong to the original run), and ``title_offered`` stays None (old
    reports did not store the grounding hints).
    """
    results = []
    for ex in examples:
        if ex["id"] not in generated:
            continue
        record = _new_record(ex)
        record["generated_sparql"] = generated[ex["id"]]
        if record["generated_sparql"] is None:
            record["error"] = "No generated query in the report (pipeline error in that run)"
        results.append(_score_generated(ex, record["generated_sparql"], sparql_client, record))
    return results


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


def _available_prompt_versions() -> list[int]:
    """Every N with a prompts/nl-to-sparql-v<N>.md on disk, ascending.

    Discovered rather than hard-coded: the old fixed ``choices=[1, 2, 3, 4]``
    silently made every later prompt (v5, v6) impossible to evaluate (C17).
    """
    versions = []
    for path in (_REPO_ROOT / "prompts").glob("nl-to-sparql-v*.md"):
        suffix = path.stem.removeprefix("nl-to-sparql-v")
        if suffix.isdigit():
            versions.append(int(suffix))
    return sorted(versions)


def _is_grounded(prompt_version: int) -> bool:
    """Whether this prompt version has a ``{grounding_hints}`` slot (v5 onwards).

    The slot is in the ``# System`` section (v5) or, since ADR-026, in the
    ``# User (template)`` section (v6: hints go in the user message so the
    system prompt stays cacheable). Read from the template itself, not from a
    version cut-off, so a future prompt is classified correctly without
    touching this file.
    """
    user_template = load_user_template("nl-to-sparql", prompt_version) or ""
    return "{grounding_hints}" in load("nl-to-sparql", prompt_version) + user_template


def _entities_db_fingerprint() -> str:
    """sha256[:12] and meta.snapshot of the entities.db grounding reads.

    Grounded prompts depend on this data (the hints are computed from it), so
    two runs with the same git SHA and prompt hash can still differ if the
    database was rebuilt — the report must record which one was used (C9).
    """
    path = grounding_db.DB_PATH
    if not path.exists():
        return "missing"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()[:12]
    conn = grounding_db.get_connection()
    try:
        snapshot = dict(conn.execute("SELECT key, value FROM meta").fetchall()).get("snapshot", "?")
    finally:
        conn.close()
    return f"{digest} (snapshot {snapshot})"


def _shown_ids(prompt_version: int, examples_path: Path) -> list[str]:
    """Ids of the evaluated file's items that the prompt SHOWS as worked examples (leakage).

    Only the few-shot bank (prompts/examples.yaml) can leak, and only into a prompt with a
    ``{few_shot_block}`` slot — v1 and v5 have none (ADR-022). The k is the one the prompt is
    built with: 6 for the fixed v2–v4 prompts (``_build_pipeline``), ``FEW_SHOT_K`` for grounded
    prompts (production ``_build_prompt``). Same selection code as the prompt (``few_shot_ids``).
    Measured 2026-10-02 for v9: ex-001, 002, 015, 019 are evaluated AND shown (ADR-038).
    """
    if examples_path.resolve() != _EXAMPLES_PATH.resolve():
        return []
    template = load("nl-to-sparql", prompt_version) + (
        load_user_template("nl-to-sparql", prompt_version) or ""
    )
    if "{few_shot_block}" not in template:
        return []
    return few_shot_ids(FEW_SHOT_K if _is_grounded(prompt_version) else 6)


def _scored(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The items behind the headline: evaluated (gold executed) and not shown in the prompt."""
    return [r for r in results if r.get("result_match") is not None and not r.get("shown")]


def _pct(k: int, n: int) -> str:
    return f"{k / n:.0%}" if n else "—"


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _headline(results: list[dict[str, Any]]) -> dict[str, Any]:
    """The three headline numbers of one run over its scored items, with 95% intervals."""
    scored = _scored(results)
    n = len(scored)
    intent = sum(r["intent_match"] is True for r in scored)
    strict = sum(r["result_match"] is True for r in scored)
    f1s = [r["f1"] for r in scored]
    return {
        "n": n,
        "intent": intent,
        "intent_ci": wilson(intent, n),
        "strict": strict,
        "strict_ci": wilson(strict, n),
        "f1": _mean(f1s),
        "f1_ci": bootstrap_ci(f1s),
        "precision": _mean([r["precision"] for r in scored]),
        "recall": _mean([r["recall"] for r in scored]),
    }


def _breakdown_rows(groups: dict[str, list[dict[str, Any]]]) -> list[str]:
    """Table rows "| group | n | macro F1 | intent | strict |" for grouped scored items."""
    rows = []
    for name, items in sorted(groups.items()):
        n = len(items)
        intent = sum(r["intent_match"] is True for r in items)
        strict = sum(r["result_match"] is True for r in items)
        rows.append(
            f"| {name} | {n} | {_mean([r['f1'] for r in items]):.2f} | "
            f"{intent} ({_pct(intent, n)}) | {strict} ({_pct(strict, n)}) |"
        )
    return rows


def _cause_rows(items: list[dict[str, Any]]) -> list[str]:
    """Table rows "| cause | n | item ids |", most frequent cause first."""
    by_cause: dict[str, list[str]] = {}
    for r in items:
        by_cause.setdefault(r["cause"] or "?", []).append(r["id"])
    ordered = sorted(by_cause.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    return [f"| {cause} | {len(ids)} | {', '.join(ids)} |" for cause, ids in ordered] or [
        "| — | 0 | |"
    ]


def _render_report(
    results: list[dict[str, Any]],
    prompt_version: int,
    provider: str,
    model: str,
    run_at: str,
    git_sha: str,
    prompt_sha: str,
    examples_sha: str,
    examples_name: str = "examples.yaml",
    grounded: bool = False,
    entities_db: str = "n/a",
    shown_ids: list[str] | None = None,
    extra_provenance: list[tuple[str, str]] | None = None,
) -> str:
    """Render the Markdown eval report from per-item result records (ADR-038 layout).

    Sections: Provenance · Summary (macro F1 QALD = the headline, then intent and strict, each
    with a 95% interval, over the SCORED items; one bridge row "strict over all items" = the
    basis of the pre-ADR-038 reports) · Shown in the prompt (not scored) · Per answer type ·
    Per query shape · Error analysis by cause · Per-example results.

    WHY MACRO F1 IS THE HEADLINE (user decision 2026-10-02, after checking the literature)
    -------------------------------------------------------------------------------------
    It is the established metric for question answering over knowledge graphs: QALD-9 ranks
    systems by "Macro F1 QALD" (CEUR-WS Vol-2241 p. 62) and TEXT2SPARQL'25 by the per-question
    F1 average (CEUR-WS Vol-4094, preface). Intent-based match (Floratou et al. 2024) is a recent
    proposal for SQL that we adapt; strict is this harness's own baseline.

    SCORED vs EXCLUDED
    ------------------
    Scored = gold executed (not broken) AND not shown in the prompt (``record["shown"]``, set by
    _run from ``shown_ids``). Broken-gold items have no score; shown items are scored but listed
    apart, because the model saw their gold query.

    STATUS SYMBOLS (per-example headers) — the item's pass/fail verdict by the intent rule (F1
    is a 0–1 score per item, given on the line below):
    PASS = intent True · FAIL = intent False · SKIP = not scored (broken gold)
    """
    shown_ids = shown_ids or []
    evaluated = [r for r in results if r.get("result_match") is not None]
    scored = _scored(results)
    shown = [r for r in evaluated if r.get("shown")]
    broken_gold = [r for r in results if r.get("broken_gold")]
    h = _headline(results)
    strict_all = sum(r["result_match"] is True for r in evaluated)
    ast_evalable = [r for r in scored if r.get("ast_match") is not None]
    ast_passed = sum(r["ast_match"] is True for r in ast_evalable)

    total_input = sum(r.get("input_tokens", 0) for r in results)
    total_output = sum(r.get("output_tokens", 0) for r in results)
    total_time = sum(r.get("duration_s", 0.0) for r in results)

    lines = [
        # "greek": fixed since ADR-033 (Greek only), kept for continuity with earlier reports.
        f"# Eval Report — prompt v{prompt_version} | {provider}/{model} | greek | {run_at}",
        "",
        "## Provenance",
        "",
        "| Field | Value |",
        "|---|---|",
        f"| git HEAD | `{git_sha}` |",
        f"| nl-to-sparql-v{prompt_version}.md sha256[:12] | `{prompt_sha}` |",
        f"| {examples_name} sha256[:12] | `{examples_sha}` |",
        "| system prompt | "
        + ("per-question grounding (production `_build_prompt`)" if grounded
           else "fixed, no grounding hints") + " |",
        f"| entities.db sha256[:12] | `{entities_db}` |",
        "| metrics | macro F1 QALD (headline), intent-based match, strict execution match "
        "(ADR-038) |",
        f"| shown in the prompt (not scored) | {', '.join(sorted(shown_ids)) or 'none'} |",
    ]
    lines += [f"| {field} | {value} |" for field, value in extra_provenance or []]

    (ilo, ihi), (slo, shi), (flo, fhi) = h["intent_ci"], h["strict_ci"], h["f1_ci"]
    lines += [
        "",
        "## Summary",
        "",
        f"Scored items: {h['n']}"
        + (f" ({len(shown)} more are shown in the prompt — not scored, see below)" if shown else "")
        + ". 95% intervals: Wilson for rates, bootstrap (10,000 resamples) for macro F1.",
        "",
        "| Metric | Value | 95% interval |",
        "|---|---|---|",
        f"| Macro F1 QALD (headline) — mean per-item F1 (P / R) | **{h['f1']:.2f}** "
        f"(P {h['precision']:.2f} / R {h['recall']:.2f}) | {flo:.2f}–{fhi:.2f} |",
        f"| Intent-based match | {h['intent']}/{h['n']} = {_pct(h['intent'], h['n'])} | "
        f"{ilo:.0%}–{ihi:.0%} |",
        f"| Strict execution match | {h['strict']}/{h['n']} = {_pct(h['strict'], h['n'])} | "
        f"{slo:.0%}–{shi:.0%} |",
        f"| Strict, all items incl. shown (pre-ADR-038 basis) | {strict_all}/{len(evaluated)} = "
        f"{_pct(strict_all, len(evaluated))} | |",
        f"| AST canonical match (secondary) | {ast_passed}/{len(ast_evalable)} = "
        f"{_pct(ast_passed, len(ast_evalable))} | |",
        f"| Broken-gold excluded | {len(broken_gold)} | |",
        f"| Total input tokens | {total_input} | |",
        f"| Total output tokens | {total_output} | |",
        f"| Total wall time (s) | {total_time:.1f} | |",
        "",
        "## Shown in the prompt (not scored)",
        "",
    ]
    if shown:
        lines += [
            "Worked examples of the prompt's few-shot block: the model saw their gold query, so "
            "they do not test it (leakage, ADR-038).",
            "",
            "| Item | Intent | Strict | F1 |",
            "|---|---|---|---|",
        ]
        lines += [
            f"| {r['id']} | {r['intent_match']} | {r['result_match']} | {r['f1']:.2f} |"
            for r in shown
        ]
    else:
        lines.append("None — no evaluated item is a worked example of this prompt.")

    lines += [
        "",
        "## Per answer type",
        "",
        "Read from the gold result: count = one row of numbers, zero-or-no = a gold that says "
        "\"none\" (COUNT 0 / ASK false — answered by 0, ASK false or no rows), list = anything "
        "else.",
        "",
        "| Answer type | n | Macro F1 | Intent | Strict |",
        "|---|---|---|---|---|",
    ]
    by_kind: dict[str, list[dict[str, Any]]] = {}
    by_shape: dict[str, list[dict[str, Any]]] = {}
    for r in scored:
        by_kind.setdefault(r["answer_kind"], []).append(r)
        by_shape.setdefault(r["query_shape"], []).append(r)
    lines += _breakdown_rows(by_kind)
    lines += [
        "",
        "## Per-shape accuracy",
        "",
        "| Query shape | n | Macro F1 | Intent | Strict |",
        "|---|---|---|---|---|",
    ]
    lines += _breakdown_rows(by_shape)

    artefacts = [r for r in scored if r["intent_match"] and not r["result_match"]]
    failures = [r for r in scored if not r["intent_match"]]
    lines += [
        "",
        "## Error analysis by cause",
        "",
        "Metric artefacts — strict fails, intent passes (the answer is right, the strict rule "
        "is not):",
        "",
        "| Cause | n | Items |",
        "|---|---|---|",
        *_cause_rows(artefacts),
        "",
        "Real failures — intent fails:",
        "",
        "| Cause | n | Items |",
        "|---|---|---|",
        *_cause_rows(failures),
    ]
    titled = [r for r in scored if r.get("title_offered") is not None]
    if titled:
        offered = [r for r in titled if r["title_offered"]]
        missed = [r for r in titled if not r["title_offered"]]
        lines += [
            "",
            "Intent passes by whether grounding offered the expected title(s) (S44's split): "
            f"offered {sum(bool(r['intent_match']) for r in offered)}/{len(offered)} · "
            f"not offered {sum(bool(r['intent_match']) for r in missed)}/{len(missed)} — "
            f"not offered: {', '.join(r['id'] for r in missed) or 'none'}.",
        ]

    lines += ["", "## Per-example results", ""]
    for r in results:
        im, rm = r.get("intent_match"), r.get("result_match")
        status = "PASS" if im is True else ("FAIL" if im is False else "SKIP")
        tag = " · shown in prompt (not scored)" if r.get("shown") else ""
        lines.append(f"### [{status}] {r['id']} — {r['query_shape']}{tag}")
        lines.append(f"**Q:** {r['question']}")
        if r.get("broken_gold"):
            lines.append(
                "**Warning: Gold SPARQL failed to execute — excluded from metrics "
                "(infra/gold issue, not a model failure).**"
            )
        if r.get("error"):
            lines.append(f"**Error:** `{r['error']}`")
        f1 = (
            f"{r['f1']:.2f} (P {r['precision']:.2f} / R {r['recall']:.2f})"
            if r.get("f1") is not None else "—"
        )
        offered = (
            f" | **Title offered:** {r['title_offered']}"
            if r.get("title_offered") is not None else ""
        )
        lines.append(
            f"**Intent:** {im} | **Strict:** {rm} | **F1:** {f1} | "
            f"**Kind:** {r.get('answer_kind') or '—'} | **Cause:** {r.get('cause') or '—'}{offered}"
        )
        toks = f"tokens: {r.get('input_tokens', 0)}in/{r.get('output_tokens', 0)}out"
        lines.append(
            f"**AST match:** {r.get('ast_match')} | **Time:** {r.get('duration_s', 0):.1f}s | {toks}"
        )
        # Show the gold SPARQL whenever a metric failed, so the reader can spot the difference.
        if r.get("gold_sparql") and (rm is False or im is False):
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


def _report_json(results: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    """The JSON sidecar of a report: run metadata + every per-item record (all scores).

    It is what scripts/compare_runs.py pairs between two runs — no Markdown parsing needed.
    """
    return {"meta": meta, "items": [dict(r) for r in results]}


def _render_runs_summary(
    runs: list[list[dict[str, Any]]], *, title: str, shown_ids: list[str]
) -> str:
    """Summary of N runs of the same set (--runs N): spread of each metric and per-item stability.

    LLM output varies between runs even at "deterministic" settings (Atil et al.,
    arXiv:2408.04667: up to 15% accuracy). Per run: the three numbers (macro F1 first — the
    headline); across runs: mean ± SD (sample SD) and min–max; per item: its mean F1 and in how
    many runs it passed (intent / strict) — an item that passes 1/3 is not a stable success.
    """
    heads = [_headline(run) for run in runs]
    lines = [
        f"# Eval runs summary — {title} | {len(runs)} uncached runs",
        "",
        f"Shown in the prompt (not scored): {', '.join(sorted(shown_ids)) or 'none'}. Each run "
        "has its own report (…-runK.md) and JSON sidecar.",
        "",
        "## Per run",
        "",
        "| Run | Scored | Macro F1 (headline) | Intent | Strict |",
        "|---|---|---|---|---|",
    ]
    for i, h in enumerate(heads, 1):
        lines.append(
            f"| {i} | {h['n']} | {h['f1']:.2f} | {h['intent']}/{h['n']} = "
            f"{_pct(h['intent'], h['n'])} | {h['strict']}/{h['n']} = {_pct(h['strict'], h['n'])} |"
        )

    def spread(values: list[float], fmt: str) -> str:
        sd = statistics.stdev(values) if len(values) > 1 else 0.0
        return (
            f"{format(_mean(values), fmt)} ± {format(sd, fmt)} | "
            f"{format(min(values), fmt)}–{format(max(values), fmt)}"
        )

    rates = {
        "Intent-based match": [h["intent"] / h["n"] if h["n"] else 0.0 for h in heads],
        "Strict execution match": [h["strict"] / h["n"] if h["n"] else 0.0 for h in heads],
    }
    lines += ["", "## Spread across runs", "", "| Metric | Mean ± SD | Min–max |", "|---|---|---|"]
    lines.append(f"| Macro F1 QALD (headline) | {spread([h['f1'] for h in heads], '.2f')} |")
    lines += [f"| {name} | {spread(values, '.0%')} |" for name, values in rates.items()]

    per_item: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        for r in _scored(run):
            per_item.setdefault(r["id"], []).append(r)
    lines += [
        "",
        "## Per-item stability (scored items)",
        "",
        "| Item | Mean F1 | Intent passes | Strict passes |",
        "|---|---|---|---|",
    ]
    for item_id, records in per_item.items():
        n = len(records)
        lines.append(
            f"| {item_id} | {_mean([r['f1'] for r in records]):.2f} | "
            f"{sum(bool(r['intent_match']) for r in records)}/{n} | "
            f"{sum(bool(r['result_match']) for r in records)}/{n} |"
        )
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Reading an existing report (--rescore)
# ---------------------------------------------------------------------------

_REPORT_HEADER = re.compile(r"^# Eval Report — prompt v(\d+) \| ([^/|]+)/(\S+) \|", re.M)
_EXAMPLES_ROW = re.compile(r"^\| (\S+\.yaml) sha256\[:12\] \| `([^`]*)` \|", re.M)
_PROVENANCE_ROW = re.compile(r"^\| ([^|]+?) \| `?([^|`]*)`? \|$", re.M)
_ITEM_HEADER = re.compile(r"^### \[(?:PASS|FAIL|SKIP)\] (\S+)", re.M)


def _parse_report(text: str) -> tuple[dict[str, Any], dict[str, str | None]]:
    """Read an eval report: (run metadata, item id → generated SPARQL or None).

    Works for every report this harness has written (old and new layouts): the header gives
    the prompt version and provider/model, the Provenance table the examples file and its
    hash, and each "### [PASS|FAIL|SKIP] id" block its "Generated SPARQL" details (None when
    the pipeline failed and no query was recorded). The S49 parsing, made reusable.
    """
    head = _REPORT_HEADER.search(text)
    if head is None:
        raise ValueError("not an eval report: no '# Eval Report — prompt vN | provider/model' header")
    examples = _EXAMPLES_ROW.search(text)
    meta = {
        "prompt_version": int(head[1]),
        "provider": head[2].strip(),
        "model": head[3].strip(),
        "examples_name": examples[1] if examples else "examples.yaml",
        "examples_sha": examples[2] if examples else "",
    }
    generated: dict[str, str | None] = {}
    for m in _ITEM_HEADER.finditer(text):
        block = text[m.end():].split("\n### ", 1)[0]
        query = None
        if "Generated SPARQL" in block:
            part = block.split("Generated SPARQL", 1)[1]
            if "```sparql\n" in part:
                query = part.split("```sparql\n", 1)[1].split("```", 1)[0].strip()
        generated[m[1]] = query
    return meta, generated


def _provenance_rows(text: str) -> dict[str, str]:
    """The Provenance table of a report as {field: value} (backticks removed)."""
    section = text.split("## Provenance", 1)[-1].split("\n## ", 1)[0]
    return {m[1].strip(): m[2].strip() for m in _PROVENANCE_ROW.finditer(section)}


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

    TWO KINDS OF PROMPT: FIXED (v1-v4) AND GROUNDED (v5 onwards)
    --------------------------------------------------------------
    v1-v4 have no ``{grounding_hints}`` slot: their system prompt (ontology
    summary + few-shot block, k=6 as always for these versions) is the same for
    every question, so it is built ONCE here and reused — cheap, identical for
    every example, and stable for the DiskCache.

    Grounded prompts (any version whose template has ``{grounding_hints}``,
    i.e. v5, v6, …) depend on the question: the hints are computed from it.
    For them the prompt is built PER QUESTION by production's own
    ``QueryPipeline._build_prompt`` (system + user message — ADR-026) (same few-shot k, same grounding code),
    with the requested ``prompt_version``. Before this, the harness only
    accepted v1-v4 and filled a single prompt without hints, so the production
    prompt could never be evaluated (title-linking plan, finding C17). Reusing
    the production builder instead of a second copy is what keeps "eval of v6"
    and "what the API serves" identical. The DiskCache still hits on reruns:
    same question → same hints → same system string.

    Parameters
    ----------
    prompt_version : int
        Which prompts/nl-to-sparql-v<N>.md to use (see ``_available_prompt_versions``).
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
    grounded = _is_grounded(prompt_version)

    fixed_system: str | None = None
    if not grounded:
        if prompt_version == 1:
            fixed_system = fill(load("nl-to-sparql", 1), ontology_summary=ontology)
        else:
            # v2-v4: static few-shot examples via {few_shot_block}.
            # select_few_shot(k=6) picks one example per query_shape, sorted by
            # few_shot_priority, and formats them as a text block for injection.
            fixed_system = fill(
                load("nl-to-sparql", prompt_version),
                ontology_summary=ontology,
                few_shot_block=select_few_shot(k=6),
            )

    class _GenerateOnlyPipeline(QueryPipeline):
        """QueryPipeline subclass that generates SPARQL but skips GraphDB.

        The parent class's run() builds the system prompt and then calls
        _generate_with_retry() followed by SparqlClient.execute(). This override
        builds the prompt (fixed for v1-v4, production's per-question
        ``_build_prompt`` for grounded versions), calls only
        _generate_with_retry(), and returns an empty PipelineResult.

        GraphDB execution is intentionally omitted here — the eval harness
        (_eval_example) executes both the gold and generated queries in the
        right order with the right error handling.

        ``fixed_system`` and ``ontology`` are captured from _build_pipeline's
        scope via closure — no extra constructor arguments needed.
        """

        def run(self, question: str) -> PipelineResult:  # type: ignore[override]
            if fixed_system is not None:
                system, user = fixed_system, question
            else:
                system, user = self._build_prompt(question)
            # Kept for the report's "title offered" check (_title_offered): the grounding
            # hints this question got are in the user message since ADR-026.
            self.last_user = user
            sparql, ti, to, retries = self._generate_with_retry(system, user, ontology)
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

    return _GenerateOnlyPipeline(
        provider=provider,
        sparql_client=sparql_client,
        provider_name=provider_name,
        model_name=model,
        prompt_version=prompt_version,
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

    ONE PASS, GREEK ONLY (ADR-033)
    ------------------------------
    Every example runs once, with its question_greek: N examples → N result records.
    (Until ADR-033 `--language both` — the default — ran every example twice, the
    second time with an English translation users never type.)

    PROVENANCE GATHERING
    --------------------
    After all examples finish, the git SHA and file hashes are collected and
    written into the report header. Collecting provenance at the END (not the
    START) ensures the hashes reflect the actual state of files when the run
    completed — if you edited a prompt mid-run, the hash will reflect the
    edited version.
    """
    # A Windows console may use a legacy code page (cp1253) without "→"/"−" — print UTF-8.
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    args = _build_arg_parser().parse_args()
    _run(args)


def _build_arg_parser() -> argparse.ArgumentParser:
    """The command-line options (see the module docstring). Separate so tests can read them."""
    parser = argparse.ArgumentParser(description="Eval harness for NL->SPARQL.")
    parser.add_argument(
        "--prompt-version",
        type=int,
        default=PROMPT_VERSION,
        choices=_available_prompt_versions(),
        help=f"Prompt version (default: {PROMPT_VERSION}, the production prompt). "
        "Versions with a {grounding_hints} slot get per-question grounding.",
    )
    parser.add_argument(
        "--examples-file",
        type=Path,
        default=_EXAMPLES_PATH,
        help="Gold example file (default: prompts/examples.yaml). Same schema, e.g. a "
        "separate title or department eval set kept out of the few-shot bank.",
    )
    parser.add_argument("--provider", default="claude", choices=["claude", "gemini", "fake"])
    parser.add_argument("--model", default="claude-haiku-4-5")
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
    parser.add_argument(
        "--split",
        choices=["dev", "test"],
        default=None,
        help="Run only items of this split (eval-titles.yaml, ADR-034); items without a split "
        "(examples.yaml) always run",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        metavar="N",
        help="Run the set N times (N > 1 needs --no-cache): one report per run + a summary of "
        "the spread (ADR-038)",
    )
    parser.add_argument(
        "--rescore",
        type=Path,
        default=None,
        metavar="REPORT",
        help="Score the generated queries of an existing report again (no LLM call); the "
        "examples file and prompt version are read from the report (ADR-038)",
    )
    return parser


def _filter_split(examples: list[dict[str, Any]], split: str | None) -> list[dict[str, Any]]:
    """Keep the items of ``split``; items that have no split are never filtered out (ADR-034).

    The title eval set is split dev/test by title family (decision 3): tune on dev, run test once.
    """
    if split is None:
        return examples
    return [e for e in examples if e.get("split", split) == split]


def _load_gold_file(examples_path: Path) -> list[dict[str, Any]]:
    """Load a gold file and validate it before any token is spent (see ``main``).

    Every comparison_mode must be known (a typo would make every comparison fail silently) and
    every gold query (except NOT_ANSWERABLE comments) must parse — checked on ALL items, not only
    the selected ones, so a broken skip_eval item is caught too.
    """
    if not examples_path.exists():
        sys.exit(f"ERROR: examples file not found: {examples_path}")
    raw = yaml.safe_load(examples_path.read_text(encoding="utf-8"))
    all_examples: list[dict[str, Any]] = raw.get("examples", [])

    for ex in all_examples:
        mode = ex.get("comparison_mode", "")
        if mode not in _KNOWN_COMPARISON_MODES:
            sys.exit(f"ERROR: example {ex.get('id')} has unknown comparison_mode={mode!r}")

    broken_gold: list[str] = []
    for ex in all_examples:
        if ex.get("comparison_mode") == "not-answerable":
            continue
        err = validate_sparql(ex["gold_sparql"].strip())
        if err:
            broken_gold.append(f"  {ex['id']}: {err[:80]}")
    if broken_gold:
        sys.exit(
            f"ERROR: broken gold SPARQL in {examples_path.name} -- fix before running eval:\n"
            + "\n".join(broken_gold)
        )
    return all_examples


def _write_report(
    out_path: Path, results: list[dict[str, Any]], meta: dict[str, Any], **render: Any
) -> None:
    """Write the Markdown report and its JSON sidecar (same name, .json)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_render_report(results, **render), encoding="utf-8")
    sidecar = out_path.with_suffix(".json")
    sidecar.write_text(
        json.dumps(_report_json(results, meta), ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"\nReport written to: {out_path}\n          sidecar: {sidecar.name}")


def _run(args: argparse.Namespace) -> None:
    """Validate the arguments and the gold file, run every selected example, write the reports."""
    if args.runs < 1:
        sys.exit("ERROR: --runs must be at least 1")
    if args.runs > 1 and not args.no_cache:
        sys.exit(
            "ERROR: --runs N > 1 needs --no-cache — the DiskCache would replay the same answers, "
            "so every run would be identical and the spread zero (ADR-038)."
        )
    if args.rescore is not None:
        if args.runs > 1:
            sys.exit("ERROR: --rescore re-scores one existing report; it takes no --runs")
        _rescore_report(args.rescore, args.output)
        return

    # --no-cache bypasses the DiskCache, which normally stores LLM responses on
    # disk keyed by sha256(system + user + model). Bypassing ensures fresh LLM
    # calls for every example — necessary when you want to measure true model
    # performance rather than replaying cached responses from a previous run.
    if args.no_cache:
        os.environ["LLM_CACHE_DISABLED"] = "1"

    examples_path: Path = args.examples_file
    all_examples = _load_gold_file(examples_path)

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
    examples = _filter_split(examples, args.split)
    if not examples:
        sys.exit(f"ERROR: no examples with split={args.split!r}")

    sparql_client = SparqlClient(settings.graphdb_endpoint)
    pipeline = _build_pipeline(args.prompt_version, args.provider, args.model)
    grounded = _is_grounded(args.prompt_version)
    shown_ids = _shown_ids(args.prompt_version, examples_path)
    prompt_path = _REPO_ROOT / "prompts" / f"nl-to-sparql-v{args.prompt_version}.md"

    first_run_at = datetime.now().strftime("%Y-%m-%dT%H:%M")
    if args.output:
        out_base = Path(args.output)
    else:
        # "greek" is fixed (ADR-033) — keeps names in line with the earlier -greek- reports.
        slug = f"{first_run_at[:10]}-v{args.prompt_version}-greek-{args.provider}-{args.model}"
        if examples_path.resolve() != _EXAMPLES_PATH.resolve():
            slug += f"-{examples_path.stem}"
        if args.split:
            slug += f"-{args.split}"
        out_base = _EVAL_RUNS_DIR / f"{slug}.md"

    runs: list[list[dict[str, Any]]] = []
    for run in range(1, args.runs + 1):
        run_at = datetime.now().strftime("%Y-%m-%dT%H:%M")
        print(
            f"\nRunning eval{f' (run {run}/{args.runs})' if args.runs > 1 else ''}: "
            f"prompt=v{args.prompt_version} "
            f"({'grounded, per question' if grounded else 'fixed'}) provider={args.provider} "
            f"model={args.model} examples={examples_path.name}"
        )
        results: list[dict[str, Any]] = []
        for ex in examples:
            print(f"  {ex['id']} ({ex['query_shape']}) ...", end="", flush=True)
            result = _eval_example(ex, pipeline, sparql_client)
            result["shown"] = result["id"] in shown_ids
            results.append(result)
            im, rm = result["intent_match"], result["result_match"]
            sym = "SKIP" if im is None else ("PASS" if im else "FAIL")
            note = " (shown in prompt)" if result["shown"] else ""
            print(f" {sym} intent, strict {rm}{note} ({result['duration_s']:.1f}s)")
        runs.append(results)

        # Provenance is gathered after the run: the hashes reflect the files actually used.
        out_path = (
            out_base if args.runs == 1
            else out_base.with_name(f"{out_base.stem}-run{run}{out_base.suffix}")
        )
        git_sha, prompt_sha = _git_sha(), _file_sha256(prompt_path)
        examples_sha = _file_sha256(examples_path)
        meta = {
            "prompt_version": args.prompt_version, "provider": args.provider, "model": args.model,
            "run_at": run_at, "git_sha": git_sha, "prompt_sha": prompt_sha,
            "examples_file": examples_path.name, "examples_sha": examples_sha,
            "split": args.split, "no_cache": args.no_cache, "run": run, "runs": args.runs,
            "shown_ids": shown_ids,
        }
        extra = [("run", f"{run} of {args.runs} (uncached)")] if args.runs > 1 else []
        _write_report(
            out_path, results, meta,
            prompt_version=args.prompt_version, provider=args.provider, model=args.model,
            run_at=run_at, git_sha=git_sha, prompt_sha=prompt_sha, examples_sha=examples_sha,
            examples_name=examples_path.name, grounded=grounded,
            entities_db=_entities_db_fingerprint(), shown_ids=shown_ids,
            extra_provenance=extra,
        )

    if args.runs > 1:
        summary_path = out_base.with_name(f"{out_base.stem}-runs{args.runs}-summary.md")
        summary_path.write_text(
            _render_runs_summary(
                runs, title=f"prompt v{args.prompt_version} | {args.provider}/{args.model} | "
                f"{examples_path.name}{f' ({args.split})' if args.split else ''}",
                shown_ids=shown_ids,
            ),
            encoding="utf-8",
        )
        print(f"Runs summary written to: {summary_path}")


def _rescore_report(report_path: Path, output: str | None) -> None:
    """--rescore: score an existing report's generated queries with today's rules (no LLM).

    The examples file and prompt version come from the report itself; the gold queries are
    re-executed from TODAY's file (a warning says so if its hash changed since the run). The
    new report keeps the original run's provenance (git HEAD, prompt hash, entities.db) and
    adds who scored it and when. Output: <report>-rescored.md (+ .json) unless --output.
    """
    text = report_path.read_text(encoding="utf-8")
    meta, generated = _parse_report(text)
    original = _provenance_rows(text)
    examples_path = _REPO_ROOT / "prompts" / meta["examples_name"]
    all_examples = _load_gold_file(examples_path)
    examples_sha = _file_sha256(examples_path)
    if meta["examples_sha"] and meta["examples_sha"] != examples_sha:
        print(
            f"WARNING: {meta['examples_name']} changed since the report was written "
            f"({meta['examples_sha']} → {examples_sha}); today's gold queries are used."
        )
    unknown = sorted(set(generated) - {e["id"] for e in all_examples})
    if unknown:
        print(f"WARNING: items no longer in {meta['examples_name']} are skipped: {unknown}")

    print(f"\nRe-scoring {report_path.name}: {len(generated)} items, no LLM call")
    results = _rescore(all_examples, generated, SparqlClient(settings.graphdb_endpoint))
    shown_ids = _shown_ids(meta["prompt_version"], examples_path)
    for r in results:
        r["shown"] = r["id"] in shown_ids

    scored_at = datetime.now().strftime("%Y-%m-%dT%H:%M")
    run_at = text.splitlines()[0].rsplit("|", 1)[-1].strip()  # header: "… | greek | <run_at>"
    out_path = Path(output) if output else report_path.with_name(f"{report_path.stem}-rescored.md")
    prompt_field = f"nl-to-sparql-v{meta['prompt_version']}.md sha256[:12]"
    scorer_sha = _git_sha()
    extra = [
        ("rescored from", f"`{report_path.name}` — its generated queries; no LLM call"),
        ("scored by", f"git `{scorer_sha}`, {scored_at} (ADR-038 metrics)"),
        (f"{meta['examples_name']} at the original run", f"`{meta['examples_sha'] or '?'}`"),
    ]
    run_meta = {
        **meta, "run_at": run_at, "git_sha": original.get("git HEAD", "?"),
        "prompt_sha": original.get(prompt_field, "?"), "examples_file": meta["examples_name"],
        "examples_sha_now": examples_sha, "rescored_from": report_path.name,
        "scored_by": scorer_sha, "scored_at": scored_at, "shown_ids": shown_ids,
    }
    _write_report(
        out_path, results, run_meta,
        prompt_version=meta["prompt_version"], provider=meta["provider"], model=meta["model"],
        run_at=run_at, git_sha=original.get("git HEAD", "?"),
        prompt_sha=original.get(prompt_field, "?"), examples_sha=examples_sha,
        examples_name=meta["examples_name"],
        grounded="per-question" in original.get("system prompt", ""),
        entities_db=original.get("entities.db sha256[:12]", "n/a"), shown_ids=shown_ids,
        extra_provenance=extra,
    )


if __name__ == "__main__":
    main()
