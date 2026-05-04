# ADR-006: Static few-shot prompt v2 and deferred dynamic retrieval

- **Status:** Accepted
- **Date:** 2026-05-04
- **Deciders:** @manoliss

## Context

After establishing the eval methodology (ADR-005) and building the 21-entry gold example bank (`prompts/examples.yaml`, promoted from 18 hand-written queries in `notes/draftedQueries.txt` plus 3 NOT_ANSWERABLE entries), the next prompt improvement is to add few-shot examples. Two retrieval strategies were considered: static (hardcode N examples) and dynamic (embed questions, retrieve top-k by similarity). We also discovered that the v1 rule "never use COUNT(DISTINCT)" was too strict — scoped queries (constrained by VALUES on a specific book code) work fine; only full-graph scans crash GraphDB.

## Options considered

### Option A — Static few-shot (inject fixed examples per-request)
Inject N examples chosen once at process start, covering one example per query shape. ~2k tokens per request.
- Pros: zero new dependencies; deterministic; no cache-key complexity; examples fit comfortably in Haiku's context window.
- Cons: all N examples are shown even if irrelevant to the question; as the bank grows, a fixed selection becomes increasingly suboptimal.

### Option B — Dynamic few-shot via embedding similarity
Embed each incoming question, retrieve top-k most similar examples at runtime.
- Pros: scales to large example banks; adapts to the specific question.
- Cons: adds a multilingual embedding model dependency (~120 MB); complicates the `sha256(system+user+model)` disk cache (examples selected for the same question text may differ if the bank changes); extra latency per request; with a 21-example bank, top-3 from 21 is a 14% selection rate — barely different from "include all".

### Option C — BM25 / lexical retrieval
Lightweight keyword retrieval over question text; no embedding model.
- Pros: no ML dependency; handles Greek reasonably.
- Cons: same cache-key problem as Option B; not meaningfully better than static for 21 examples.

## Decision

We chose **Option A (static few-shot)** for v2.

The example bank has 21 entries covering ~9 distinct query shapes. With such a small, shape-diverse bank, dynamic retrieval selects examples that are barely different from a well-chosen static set — and introduces real operational complexity (new dependency, cache invalidation). The right condition to revisit this is: bank grows past ~40 examples, OR static few-shot plateaus on a measurable eval axis (i.e., specific shapes consistently generate wrong answers despite being in the bank). Neither condition holds today.

The six examples injected via `examples_loader.select_few_shot(k=6)` cover: traversal-lookup, negative-existence, multi-level-aggregate-with-concat, set-difference-by-year, set-difference-by-book, and set-intersection-by-book — the patterns most likely to trip the LLM.

## Consequences

- **Prompt token cost increases** by ~2k tokens per request (6 examples). At Haiku pricing this is negligible (~$0.0006/request).
- **Disk cache remains valid**: the few-shot block is stable across requests (module-level singleton), so `sha256(system+user+model)` still uniquely identifies identical calls. Cache is NOT invalidated when `examples.yaml` changes — restart the process to pick up new examples.
- **Dynamic retrieval is explicitly deferred.** Conditions to revisit: bank > ~40 examples, or static eval accuracy plateaus for a specific shape. When that condition is met, BM25 first (zero deps, 50 lines), then `multilingual-e5-small` embeddings if BM25 underperforms.
- **COUNT(DISTINCT) rule corrected.** v2 rule 10 replaces the v1 blanket ban with a scoped-only policy. The scope boundary is: `COUNT(DISTINCT)` inside an aggregate is safe when the query is constrained to a small entity via `VALUES ?code`; it crashes for full-graph scans (Q17/Q18 behaviour, confirmed 2026-05-04).
- **Two new prompt rules added** (rules 11 and 12): GROUP_CONCAT deduplication via inner subquery, and the Course-vs-Module disambiguation. These were implicit in v1; v2 makes them explicit because they represent real failure modes.

## Follow-ups

- [ ] Run baseline eval (v1, `--language both`) and persist report.
- [ ] Run v2 eval and compare.
- [ ] Revisit Greek NL phrasings in `prompts/examples.yaml` (all marked TODO).
- [ ] Investigate whether Q17/Q18 are feasible with a subquery rewrite.
- [ ] Update `decisions/README.md` index.
