# Thesis outline (living document)

_Write first, trim later. Each bullet = a paragraph or two. Update as your work evolves._

## 0. Abstract / Περίληψη (~300 words)

- The problem: SPARQL is a barrier to KG access.
- Our approach: LLM as NL→SPARQL translator, grounded in the ontology.
- Our case study: EvdoGraph.
- Our contributions: (a) working system, (b) comparison across LLM providers, (c) evaluation methodology.
- Key results (fill in after Ch. 6).

## 1. Εισαγωγή / Introduction

- Motivation: knowledge is locked behind query languages.
- Who benefits: students, librarians, general public.
- Research questions:
  - RQ1: Can modern LLMs reliably translate Greek-language questions about EvdoGraph into correct SPARQL?
  - RQ2: How does accuracy vary across providers (Claude / OpenAI / open-source)?
  - RQ3: What role does ontology context play in prompt design?
- Contributions (bulleted).
- Thesis structure (one paragraph per chapter).

## 2. Θεωρητικό Υπόβαθρο / Theoretical Background

- 2.1 Large Language Models: brief history, training, capabilities, limitations.
- 2.2 Knowledge Graphs: RDF triples, graph model, examples.
- 2.3 Ontologies: OWL, classes, properties, why they matter for query generation.
- 2.4 SPARQL: syntax, execution, SPARQL 1.1 features we use.
- 2.5 EvdoGraph: its origin, schema at a high level, statistics.

## 3. Σχετικές Εργασίες / Related Work

- NL→SPARQL before LLMs (template-based systems, semantic parsing).
- Text-to-SQL literature as a parallel (Spider, WikiSQL benchmarks).
- Recent LLM-based NL→SPARQL work (e.g. SparqlGPT-style systems).
- RAG over knowledge graphs.
- Gap our work addresses (Greek-language, EvdoGraph specifically, provider comparison).

## 4. Σχεδιασμός Συστήματος / System Design

- 4.1 Requirements and constraints.
- 4.2 Architecture diagram + walkthrough.
- 4.3 LLM abstraction layer (why pluggable — rewrite of ADR-002).
- 4.4 Prompt design strategy.
- 4.5 Ontology summarization (the "whole ontology doesn't fit" problem and our approach).
- 4.6 Error recovery (invalid SPARQL → retry).
- 4.7 UI design choices.

## 5. Υλοποίηση / Implementation

- Stack overview.
- Backend walkthrough (key modules).
- Frontend walkthrough.
- Deployment (if applicable).
- Selected code snippets for interesting parts.

## 6. Αξιολόγηση / Evaluation

- 6.1 Evaluation methodology: test set design, correctness criteria (exact match? execution match?), metrics (accuracy, latency, cost).
- 6.2 Test set: ~20-30 NL→SPARQL pairs for EvdoGraph.
- 6.3 Results per provider/model.
- 6.4 Error analysis: common failure modes (bad property names, wrong FILTER syntax, hallucinated URIs...).
- 6.5 Prompt ablations (with/without ontology, few-shot vs. zero-shot).

## 7. Συμπεράσματα / Conclusions

- Summary of findings.
- Limitations.
- Future work: more KGs, more models, fine-tuning, interactive clarification dialogs.

## 8. Παράρτημα / Appendix

- Full test set.
- Selected prompt templates.
- Installation and reproduction instructions.

---

## Status tracker

| Chapter | Draft | Reviewed | Final |
|---|---|---|---|
| 00 Abstract | ☐ | ☐ | ☐ |
| 01 Intro | ☐ | ☐ | ☐ |
| 02 Background | ☐ | ☐ | ☐ |
| 03 Related Work | ☐ | ☐ | ☐ |
| 04 System Design | ☐ | ☐ | ☐ |
| 05 Implementation | ☐ | ☐ | ☐ |
| 06 Evaluation | ☐ | ☐ | ☐ |
| 07 Conclusions | ☐ | ☐ | ☐ |
| 08 Appendix | ☐ | ☐ | ☐ |
