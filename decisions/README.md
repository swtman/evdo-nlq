# Architecture Decision Records

An **ADR** is a short markdown file capturing a meaningful technical decision: what we chose, what the alternatives were, why we chose it, and what we accept as a consequence.

## Why we do this

1. **Future-you and future-Claude-sessions understand the code.** When a CLAUDE.md says "use FastAPI", the ADR tells you why — so you don't second-guess it next month.
2. **Your thesis Chapter 04 (System Design) writes itself.** Each ADR is already a miniature design-decision section. You rewrite them into prose, done.
3. **Your supervisor sees the reasoning trail.** When they ask "why did you do it this way?", you point at the ADR.

## When to write one

Write an ADR when you make a decision that:

- Would be annoying or costly to reverse.
- Would confuse a new collaborator (or future you) if undocumented.
- Involves a real trade-off, not just style.

Don't write one for: file naming, variable names, which CSS color to use.

## Format

Each ADR is one file: `NNN-slug.md` where `NNN` is a zero-padded number.

Use `000-template.md` as a starting point. Keep it short — 200–400 words is plenty.

## Status values

- **Proposed** — drafted, not yet acted on.
- **Accepted** — decision made, code follows it.
- **Superseded by ADR-NNN** — a later ADR replaced this one. Don't delete the old one; link forward.
- **Deprecated** — no longer relevant but kept for history.

## Index

| # | Title | Status |
|---|---|---|
| 001 | Python backend with FastAPI | Accepted |
| 002 | Pluggable LLM provider abstraction | Accepted |
| 003 | Remote GraphDB (no local triple store) | Accepted |
| 004 | NLQ pipeline design — streaming, per-request provider, retry, ontology loading | Accepted |
| 005 | Evaluation methodology for NL→SPARQL quality | Accepted |
| 006 | Static few-shot prompt v2 and deferred dynamic retrieval | Accepted |
| 007 | Anthropic prompt caching on system prefix | Accepted |
| 008 | Frontend aesthetic: parchment-brutalist design system | Accepted |
| 009 | History sidebar as header-toggle overlay, not permanent column | Accepted |
| 010 | Docker Compose as reproducibility packaging layer | Accepted |
| 011 | Ollama as the local LLM provider | Accepted |
