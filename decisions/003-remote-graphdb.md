# ADR-003: Use the remote GraphDB instance for EvdoGraph

- **Status:** Accepted
- **Date:** 2026-04-22
- **Deciders:** @swtman

## Context

EvdoGraph is already hosted on the CSD lab's server at `http://lod.csd.auth.gr:7200/` (GraphDB, default port 7200). We need to decide whether to use that endpoint directly or stand up a local GraphDB instance loaded with a snapshot of the data.

## Options considered

### Option A — Use the remote endpoint as-is
- Pros: Zero setup. Always up to date. The exact data the thesis refers to. One less service to run locally.
- Cons: Depends on the university network being up and the lab keeping the endpoint alive. Latency is higher than localhost. No write access (fine — we are read-only anyway).

### Option B — Local GraphDB running an EvdoGraph dump
- Pros: Reproducible, offline-capable, low latency. Good for isolated evaluation runs.
- Cons: Requires obtaining a dump, installing GraphDB, loading it. Another moving part. Data may drift from the canonical version.

### Option C — Local Apache Jena Fuseki running an EvdoGraph dump
- Pros: free, simple single JAR.
- Cons: Same drawbacks as Option B plus: Fuseki's query behaviour may differ subtly from GraphDB's (they implement SPARQL 1.1 with different extensions).

## Decision

We chose **Option A — the remote GraphDB endpoint** at `http://lod.csd.auth.gr:7200/repositories/Evdoxus`.

## Consequences

- We require network access during development and evaluation.
- All SPARQL results are authoritative (no staleness).
- If the endpoint goes down near a deadline, we have no fallback. **Mitigation:** keep `scripts/dump_ontology.py` running periodically so we at least have the schema cached locally, and cache past query results during evaluation so a re-run isn't fully gated on live access.
- Endpoint URL is configured via `GRAPHDB_ENDPOINT` in `.env`, so switching to a local instance later is a one-line change.

## Follow-ups

- [ ] Verify the exact repository path (`/repositories/evdograph` or similar) via GraphDB's Workbench UI at the root URL.
- [ ] Save an ontology snapshot to `notes/evdograph-ontology-snapshot.ttl` as a safety net.
