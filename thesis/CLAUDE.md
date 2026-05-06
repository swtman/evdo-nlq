# thesis/ — Thesis document (Greek)

The thesis itself. Greek text, English code/figures where applicable.

## Format decision (TBD — see ADR-006 when written)

Two viable options, pick one and commit:

- **LaTeX** — standard for AUTh CS. Reproducible, great math and references, version-controlled cleanly. Steeper learning curve. Use `latexmk` or Overleaf.
- **Markdown → .docx via Pandoc** — faster to write, easy for Claude Code to edit, cheap to export to `.docx` for supervisor review. Bibliography via `pandoc-citeproc` (BibTeX input).

**Recommendation for your timeline:** Markdown + Pandoc. You can always convert to LaTeX later if your supervisor insists. The `anthropic-skills:docx` skill works natively with `.docx`, so producing drafts for supervisor review is one command.

## Layout

```
thesis/
├── CLAUDE.md           (this file)
├── outline.md          chapter-by-chapter outline (living document)
├── chapters/
│   ├── 00-abstract.md
│   ├── 01-introduction.md
│   ├── 02-background.md        LLMs, KGs, ontologies, SPARQL, EvdoGraph
│   ├── 03-related-work.md
│   ├── 04-system-design.md     rewrites ADRs into prose
│   ├── 05-implementation.md
│   ├── 06-evaluation.md
│   ├── 07-conclusions.md
│   └── 08-appendix.md
├── figures/            diagrams, screenshots, charts (SVG preferred)
├── papers/             cited PDFs (NOT committed by default — see .gitignore)
├── references.bib      BibTeX bibliography
└── thesis.md           master file that includes chapters (for Pandoc)
```

## Writing conventions

- **Language:** Greek (modern, polytonic NOT required).
- **Person:** First person plural where appropriate ("σε αυτή την εργασία, παρουσιάζουμε...") — standard academic Greek.
- **Technical terms:** Keep English terms in parentheses on first use: "γράφος γνώσης (knowledge graph)". After first mention, use the Greek term.
- **Code in text:** use inline `code` formatting for identifiers, filenames, SPARQL fragments.
- **Figures:** caption in Greek, labels in English where they match code.
- **Math:** standard LaTeX syntax inside `$...$` — works in both LaTeX and Pandoc paths.

## Citation style

IEEE numeric `[1]` is standard for CSD thesis work. Keep all references in `references.bib`. Minimum to cite on day one:

- Brown et al., "Language Models are Few-Shot Learners" (GPT-3)
- The Anthropic Claude technical report
- "Knowledge Graphs" by Hogan et al. (ACM Computing Surveys)
- The SPARQL 1.1 W3C Recommendation
- The OWL 2 W3C Recommendation
- The EvdoGraph paper/report (ask your supervisor for the canonical citation)

## Chapter-to-artifact map (how coding work fuels writing)

| Thesis chapter | Source material you'll already have |
|---|---|
| 01 Introduction | `../README.md`, `notes/PROGRESS.md` reflections |
| 02 Background | literature review (papers in `papers/`, summaries from `anthropic-skills:pdf`) |
| 03 Related Work | papers on NL→SPARQL, text-to-SQL, RAG-over-KGs |
| 04 System Design | `../decisions/*.md` ADRs rewritten as prose + architecture diagram |
| 05 Implementation | code walkthrough, screenshots, snippets from `backend/` |
| 06 Evaluation | output of the eval harness in `backend/scripts/eval.py`; reports in `notes/eval-runs/` |
| 07 Conclusions | `notes/PROGRESS.md`, lessons learned, future work |

**This mapping is the key insight.** If you keep ADRs and PROGRESS.md up to date while coding, the writing phase is mostly translation + polish, not invention.

## Workflow with Claude

- **Drafting a chapter:** "Read `outline.md` and chapters 01-03. Draft chapter 04 System Design based on the ADRs in `../decisions/`."
- **Review pass:** "Review chapter 04 for clarity, Greek grammar, and consistency with chapters 02-03. Don't expand scope."
- **`.docx` for supervisor:** invoke the `anthropic-skills:docx` skill. Pandoc can convert chapters to a single `.docx` for review.

## What NOT to do

- Don't let Claude invent citations. Every `[N]` reference must exist in `references.bib`.
- Don't paste LLM output into the thesis verbatim without checking facts.
- Don't commit PDFs of copyrighted papers (keep them locally in `papers/`, gitignored).
