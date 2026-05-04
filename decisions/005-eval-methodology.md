# ADR-005: Evaluation methodology for NL→SPARQL quality

- **Status:** Accepted
- **Date:** 2026-05-04
- **Deciders:** @manoliss

## Context

Before improving SPARQL generation (few-shot examples, prompt v2, dynamic retrieval), we need a way to measure whether a change actually helps. The project currently has no eval set and no automated metric. We need an approach that is honest about what it measures, cheap to run on every prompt change, and defensible in a thesis chapter. Three candidate metrics were considered: exact-string match, AST/structural equivalence, and result-set equivalence (execution-based).

## Options considered

### Option A — Exact-string SPARQL match
- Pros: zero dependencies, instant.
- Cons: fails on semantically identical queries that differ in variable names, triple order, whitespace, or equivalent FILTER rewrites. Unusably strict as a primary metric.

### Option B — AST canonical equivalence (rdflib parse + canonicalize)
- Pros: already have the parser via `validate_sparql()`; catches variable-name and triple-order differences; no GraphDB required.
- Cons: misses structural rewrites that are semantically identical (property path vs joined triples, `OPTIONAL` vs `COALESCE`, etc.). Produces false negatives — biases accuracy *down*, which is conservative but not accurate.

### Option C — Result-set equivalence (execution-based)
- Pros: the gold standard in NL→SPARQL literature (Spider, LC-QuAD, KQA Pro all use execution accuracy); doesn't care how the query is written, only whether the answer matches; handles all legal rewrites; cheap (~200 ms/query × 20 examples = 4 s per full eval run).
- Cons: requires a live GraphDB connection; needs per-example metadata (`comparison_mode`: set vs ordered vs scalar) to handle `ORDER BY`/`LIMIT` and aggregate queries correctly; empty results need a flag to distinguish "correctly empty" from "wrong query".

## Decision

We chose **Option C (result-set equivalence) as the primary metric**, with **Option B (AST equivalence) as a secondary metric**.

Result-set match is the only metric that validates the *answer*, not the *form*. AST equivalence is kept as a sanity check: when it agrees with result-match, confidence is high; when they diverge, it flags an interesting rewrite case worth examining in the thesis. Option A is dropped entirely.

A manually-maintained error taxonomy (labels: `wrong_class`, `missing_filter`, `bad_aggregation`, `hallucinated_property`, `course_module_confusion`) and a per-query-shape accuracy breakdown are added as qualitative layers — this is where the thesis narrative actually lives.

## Consequences

- **Eval requires a live GraphDB connection.** CI cannot run eval automatically unless the runner has network access to `lod.csd.auth.gr`. Eval is a manual step run by the developer.
- **Gold `expected_rows` must be version-stamped.** EvdoGraph data changes each semester. Either re-execute gold queries on every eval run (preferred) or record the data snapshot date alongside each gold record.
- **Cache-key discipline.** The existing `sha256(system + user + model)` cache remains valid for eval. Gold SPARQL is run directly via `SparqlClient`, not through the LLM cache.
- **Metric drift.** Run a manual pass (Route 6 — eyeball all 20) after every major prompt change and verify it correlates with the automated metrics. If they diverge, trust the human.
- **LLM-as-judge is not used as a primary metric** because it introduces an uncontrolled bias that is hard to defend to a thesis committee. It may be used as a tiebreaker on specific disagreement cases if needed.

## Eval record format

Each gold example in `prompts/examples.yaml` must carry:

```yaml
- id: ex-001
  question_greek: "..."
  question_english: "..."
  gold_sparql: |
    SELECT ...
  query_shape: lookup | count | filter | traverse | aggregate | top-n | semester-filter | not-answerable
  comparison_mode: set | ordered | scalar | not-answerable
  notes: ""
```

## Follow-ups

- [ ] Create `prompts/examples.yaml` with scaffold and first few entries
- [ ] Create `scripts/eval.py` — runs all examples through the pipeline, reports result-set match and AST match
- [ ] Update `decisions/README.md` index
