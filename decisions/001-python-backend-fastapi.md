# ADR-001: Python backend with FastAPI

- **Status:** Accepted
- **Date:** 2026-04-22
- **Deciders:** @swtman

## Context

We need a backend that orchestrates the NL → LLM → SPARQL → GraphDB → JSON pipeline. The thesis subject explicitly lists "Python or Java" as acceptable. The developer has some Flask/FastAPI familiarity and no strong Java-backend experience. The timeline is tight (≈26 days of full focus before an internship begins).

## Options considered

### Option A — Python + FastAPI
- Pros: richest LLM ecosystem (`anthropic`, `openai` SDKs), strong RDF ecosystem (`rdflib`, `SPARQLWrapper`), fast prototyping, modern async support, automatic OpenAPI docs at `/docs`, Pydantic validation out of the box.
- Cons: dynamic typing can hide bugs; smaller Semantic Web tradition than Java.

### Option B — Java + Apache Jena + Spring Boot
- Pros: Apache Jena is the gold standard for Semantic Web. Strong typing catches errors early. Familiar to CS curricula.
- Cons: far more boilerplate, slower iteration, weaker LLM SDK ecosystem (would rely on HTTP clients), steeper learning curve on Spring Boot.

### Option C — Python + Flask
- Pros: lightest-weight Python option, familiar.
- Cons: no automatic schema validation or OpenAPI docs; async support is clumsy; FastAPI solves these by default.

## Decision

We chose **Option A — Python + FastAPI**.

The thesis's core contribution is the LLM↔KG interaction, not the web framework. Python minimises time spent on plumbing and maximises time spent on prompt engineering, evaluation, and writing. FastAPI gives us schema validation and typed request/response models effectively for free.

## Consequences

- Backend relies on `rdflib` and `SPARQLWrapper` rather than Jena. `rdflib` is less feature-rich but sufficient for our needs (we are mostly sending SPARQL and parsing JSON results; we do not reason over the graph locally).
- Package manager is `uv` (fast, modern, lockfile support) rather than plain pip.
- Pydantic models define the API contract that the frontend's TS types mirror.

## Follow-ups

- [x] Document in `backend/CLAUDE.md`
- [ ] Cite Jena vs rdflib trade-off briefly in thesis Chapter 04
