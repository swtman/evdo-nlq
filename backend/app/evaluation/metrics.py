"""Per-item scoring of a generated SPARQL answer against a gold answer (ADR-038).

THREE NUMBERS, NEVER ONE
------------------------
Every eval report gives three numbers, because each one alone misleads:

strict  ``strict_match`` — the harness's rule from ADR-005, unchanged so every report stays
        comparable with the ones written before ADR-038. Columns are compared BY POSITION
        (first gold column vs first generated column) and mode "set" is a MULTISET (a
        duplicated row is a difference). It fails correct answers whose columns come in another
        order (ex-003/004), carry one extra column (ex-011) or repeat rows (te-001, ex-016).

intent  ``intent_match`` — pass/fail. "Intent-based execution match" (Floratou et al.,
        CIDR 2024, §4 p. 5 — a recent proposal for SQL; the content mapping and the "none"
        rule below are this project's adaptations): row order is ignored unless the gold asks for it, the generated
        query may return MORE columns than the gold, and here rows are a true SET. Gold columns
        are matched to generated columns by their CONTENT, in any order (``content_mappings``).
        A gold that says "none" — a zero count or ASK false; answer kind "zero-or-no" — accepts
        every natural form of "none": ASK false, an empty SELECT, or one row of zeros
        (``says_no``). This covers yes/no questions answered "no" (te-042…047) AND "how many"
        questions whose answer is 0 (eval-departments dept-absent-01…04, found by S51): in
        SPARQL a COUNT with GROUP BY over no matches returns NO rows, not a 0, so an empty
        result is a natural way to say 0 (user decision, 2026-10-02).

F1      ``f1_qald`` — THE HEADLINE (user decision 2026-10-02): partial credit, precision /
        recall / F over the answer SETS, with QALD-9's rules for empty answers (Usbeck et al.,
        CEUR-WS Vol-2241 p. 62, "Macro F1 QALD"). The report averages F over items (macro F1).
        It is the established metric of the task: QALD-9 ranks by it, and TEXT2SPARQL'25 ranks
        by the per-question F1 average (CEUR-WS Vol-4094, preface — nDCG for the questions
        whose order matters, which this F1 does not do: order is ignored here).

WHAT A "VALUE" IS
-----------------
GraphDB returns every value as a string; an unbound variable (OPTIONAL) is ``None``. Values are
compared as returned, with ``None`` read as ``""`` (``row_values``), exactly as before.

KNOWN LIMIT (stated in ADR-038)
-------------------------------
Execution match on ONE knowledge-graph instance can accept a wrong query whose result happens
to coincide with the gold's (Zhong et al., EMNLP 2020). Matching columns by content widens this a
little: two different quantities that hold identical values in every row are indistinguishable.
That is why ``intent`` is always reported next to ``strict``, never alone.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.sparql.client import SparqlResult

# Answer kinds, read from the GOLD RESULT (not from a field of the eval file — the title set is
# frozen, ADR-034): the per-type table of the report groups items by these.
NOT_ANSWERABLE = "not-answerable"
ZERO_OR_NO = "zero-or-no"
COUNT = "count"
LIST = "list"

# Values that mean "no" in a one-row answer: a zero count, ASK false, an unbound/empty cell.
_NO_VALUES = {"0", "false", ""}


# ---------------------------------------------------------------------------
# Row helpers and the strict rule (moved verbatim from scripts/eval.py)
# ---------------------------------------------------------------------------


def row_values(row: dict[str, Any], columns: list[str] | tuple[str, ...]) -> tuple:
    """One row's values in the order of ``columns``, ``None`` read as ``""``.

    ``columns`` is normally the query's own SELECT order (``SparqlResult.columns``); the intent
    and F1 rules pass a MAPPED order instead (one generated column per gold column). ``None``
    becomes ``""`` so rows can be sorted (``sorted([None, "a"])`` raises) — both sides get the
    same treatment, so an unbound value still only matches an unbound (or empty) value.
    """
    return tuple("" if row.get(col) is None else row[col] for col in columns)


def rows_to_multiset(result: SparqlResult) -> list[tuple]:
    """All rows as a sorted list of value tuples — a multiset: order ignored, duplicates kept."""
    return sorted(row_values(r, result.columns) for r in result.rows)


def strict_match(gold: SparqlResult, gen: SparqlResult, mode: str) -> bool:
    """The strict rule (ADR-005): positional columns; "set" = multiset; "ordered" = list;
    "scalar" = exactly one row on each side. Unchanged by ADR-038 — see the module docstring.

    Raises ``ValueError`` for an unknown mode ("not-answerable" is decided before scoring).
    """
    if mode == "set":
        return rows_to_multiset(gold) == rows_to_multiset(gen)
    if mode == "ordered":
        return [row_values(r, gold.columns) for r in gold.rows] == [
            row_values(r, gen.columns) for r in gen.rows
        ]
    if mode == "scalar":
        if len(gold.rows) != 1 or len(gen.rows) != 1:
            return False
        return row_values(gold.rows[0], gold.columns) == row_values(gen.rows[0], gen.columns)
    raise ValueError(f"Unknown comparison_mode: {mode!r}")


# ---------------------------------------------------------------------------
# Answer kind and "no"
# ---------------------------------------------------------------------------


def _is_number(value: str) -> bool:
    try:
        float(value)
    except ValueError:
        return False
    return True


def answer_kind(gold: SparqlResult | None, mode: str) -> str:
    """What kind of answer the gold expects: not-answerable, zero-or-no, count or list.

    Read from the gold's RESULT, so the frozen eval files need no new field:
    - "zero-or-no": the gold says "none" — an ASK false, or one row × one column holding 0: the
      title set's yes/no items «διδάσκεται το μάθημα T στο U;» (gold COUNT 0) and "how many"
      questions whose answer is 0 (eval-departments dept-absent-*); see the module docstring;
    - "count": one row whose every value is a number (a COUNT, or several counts side by side);
    - "list": everything else (rows of names, an empty result, …).
    """
    if mode == "not-answerable" or gold is None:
        return NOT_ANSWERABLE
    if gold.boolean is False:
        return ZERO_OR_NO
    if len(gold.rows) == 1:
        values = row_values(gold.rows[0], gold.columns)
        if len(values) == 1 and values[0] == "0":
            return ZERO_OR_NO
        if values and all(_is_number(v) for v in values):
            return COUNT
    return LIST


def says_no(gen: SparqlResult) -> bool:
    """Whether a generated answer says "no": ASK false, no rows, or one row of 0/false/empty.

    These are the three ways the model answered «διδάσκεται …;» correctly in the live v9 run
    (S49/S50): ASK → false, a SELECT with no rows, a COUNT of 0.
    """
    if gen.boolean is not None:
        return gen.boolean is False
    if not gen.rows:
        return True
    if len(gen.rows) != 1:
        return False
    return all(str(v).lower() in _NO_VALUES for v in row_values(gen.rows[0], gen.columns))


# ---------------------------------------------------------------------------
# Column mapping
# ---------------------------------------------------------------------------


def _column_values(result: SparqlResult, column: str) -> set:
    """The distinct values of one column (``None`` read as ``""``)."""
    return {row_values(r, (column,))[0] for r in result.rows}


def _mappings(gold: SparqlResult, gen: SparqlResult, fits) -> Iterator[tuple[str, ...]]:
    """Every injective assignment of one generated column per gold column, where ``fits(gold
    values, generated values)`` holds for each pair — a small backtracking search."""
    gold_values = [_column_values(gold, c) for c in gold.columns]
    gen_values = {c: _column_values(gen, c) for c in gen.columns}
    candidates = [[c for c in gen.columns if fits(gv, gen_values[c])] for gv in gold_values]

    def extend(i: int, used: tuple[str, ...]) -> Iterator[tuple[str, ...]]:
        if i == len(candidates):
            yield used
            return
        for c in candidates[i]:
            if c not in used:
                yield from extend(i + 1, (*used, c))

    if gold.columns and len(gen.columns) >= len(gold.columns):
        yield from extend(0, ())


def content_mappings(gold: SparqlResult, gen: SparqlResult) -> Iterator[tuple[str, ...]]:
    """Mappings of gold columns onto generated columns WITH THE SAME DISTINCT VALUES.

    A tuple names, for each gold column in order, the generated column standing in for it.
    Requiring equal content is lossless for the intent rule (equal row sets imply equal column
    value sets) and it is what keeps a mapping from pairing two different quantities whose
    values differ — the todo's "prefer a mapping by distinct column content".
    """
    return _mappings(gold, gen, lambda g, c: g == c)


def _project(gen: SparqlResult, mapping: tuple[str, ...]) -> list[tuple]:
    """The generated rows reduced to the mapped columns, in the gold's column order."""
    return [row_values(r, mapping) for r in gen.rows]


def _distinct_in_order(rows: list[tuple]) -> list[tuple]:
    """The rows with repeats removed, first occurrence kept (``dict`` preserves order)."""
    return list(dict.fromkeys(rows))


# ---------------------------------------------------------------------------
# Intent-based match (the headline)
# ---------------------------------------------------------------------------


def intent_match(gold: SparqlResult, gen: SparqlResult, mode: str) -> bool:
    """Intent-based execution match (Floratou et al. 2024, §4) — see the module docstring.

    - a "no" gold (``answer_kind`` zero-or-no) → ``says_no(gen)``;
    - an empty gold → the generated answer must be empty too;
    - otherwise some ``content_mappings`` mapping must give: for "set" the same SET of rows; for
      "ordered" the same distinct rows in the same order; for "scalar" one distinct row, equal.
    """
    if answer_kind(gold, mode) == ZERO_OR_NO:
        return says_no(gen)
    gold_rows = [row_values(r, gold.columns) for r in gold.rows]
    if not gold_rows:
        return not gen.rows
    for mapping in content_mappings(gold, gen):
        got = _project(gen, mapping)
        if mode == "ordered":
            if _distinct_in_order(got) == _distinct_in_order(gold_rows):
                return True
        elif mode == "scalar":
            if len(set(gold_rows)) == 1 and set(got) == set(gold_rows):
                return True
        elif set(got) == set(gold_rows):
            return True
    return False


# ---------------------------------------------------------------------------
# Macro F1 QALD (partial credit)
# ---------------------------------------------------------------------------


def f1_qald(
    gold: SparqlResult, gen: SparqlResult | None, mode: str
) -> tuple[float, float, float]:
    """Precision, recall and F of one item, with QALD-9's empty-answer rules (p. 62).

    ``gen`` is ``None`` when there is no answer at all (generation failed, GraphDB rejected
    the query, or the model said NOT_ANSWERABLE to an answerable question).

    - "no" items are binary: (1, 1, 1) if ``says_no`` else (0, 0, 0) — a yes/no answer has no
      partial credit; no answer at all → (1, 0, 0) as below.
    - empty gold + empty answer → (1, 1, 1); empty gold + any answer → (0, 0, 0).
    - gold has answers + empty answer → (1, 0, 0): "Macro F1 QALD" reads it as "cannot answer",
      P = 1, R = F = 0.
    - a FAILED query on an empty gold → (0, 0, 0): an error is never a correct empty answer
      (a stated deviation from a literal reading of QALD-9 — ADR-038).
    - otherwise the answer set is the set of generated rows projected onto the gold columns;
      the mapping with the best F is used (a column qualifies if it shares at least one value
      with the gold column). No qualifying mapping → (0, 0, 0). Row order is ignored.
    """
    gold_set = {row_values(r, gold.columns) for r in gold.rows}
    if gen is None:
        return (1.0, 0.0, 0.0) if gold_set else (0.0, 0.0, 0.0)
    if answer_kind(gold, mode) == ZERO_OR_NO:
        return (1.0, 1.0, 1.0) if says_no(gen) else (0.0, 0.0, 0.0)
    if not gold_set:
        return (1.0, 1.0, 1.0) if not gen.rows else (0.0, 0.0, 0.0)
    if not gen.rows:
        return (1.0, 0.0, 0.0)
    best = (0.0, 0.0, 0.0)
    for mapping in _mappings(gold, gen, lambda g, c: bool(g & c)):
        answer = set(_project(gen, mapping))
        correct = len(answer & gold_set)
        if not correct:
            continue
        p, r = correct / len(answer), correct / len(gold_set)
        f = 2 * p * r / (p + r)
        if f > best[2]:
            best = (p, r, f)
    return best


# ---------------------------------------------------------------------------
# Failure cause (the report's error-analysis section)
# ---------------------------------------------------------------------------


def failure_cause(
    gold: SparqlResult,
    gen: SparqlResult | None,
    mode: str,
    *,
    strict: bool,
    intent: bool,
    f1: float,
    error: str | None = None,
) -> str | None:
    """A short label saying why an item did not pass every metric — ``None`` if it did.

    Metric artefacts (strict fails, intent passes — the answer is right, the strict rule is
    not): '"none" form', 'extra columns', 'duplicate rows', 'column order', checked in that
    order. Real failures (intent fails): the ``error`` label the harness passes ('pipeline
    error', 'execution error', 'said not answerable'), else 'too few columns', 'empty answer',
    'wrong rows (partial)' (F1 > 0) or 'wrong rows'.
    """
    if strict and intent:
        return None
    if error:
        return error
    if intent and gen is not None:
        if answer_kind(gold, mode) == ZERO_OR_NO:
            return '"none" form'
        if len(gen.columns) > len(gold.columns):
            return "extra columns"
        if len(set(rows_to_multiset(gen))) != len(gen.rows) or len(
            set(rows_to_multiset(gold))
        ) != len(gold.rows):
            return "duplicate rows"
        return "column order"
    if gen is None:
        return "empty answer"
    if gen.rows and len(gen.columns) < len(gold.columns):
        return "too few columns"
    if not gen.rows:
        return "empty answer"
    return "wrong rows (partial)" if f1 > 0 else "wrong rows"
