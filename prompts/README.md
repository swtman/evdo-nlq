# Prompts

Every LLM prompt used by the app lives here as a versioned Markdown file. Code loads prompts by name + version, never by inlined string.

## Naming convention

```
<purpose>-v<N>.md     e.g. nl-to-sparql-v1.md, nl-to-sparql-v2.md
```

- Bump the version number for **any meaningful change** (new few-shot examples, new instruction, changed output format).
- Never edit an old version in place once it's been used in an evaluation run — create a new `vN+1`.
- The `backend/app/prompts/loader.py` resolves `"nl-to-sparql"` to the highest version in this folder by default; pass `version=N` for explicit pinning.

## File format

Each prompt file has a small frontmatter block and three sections:

```markdown
---
name: nl-to-sparql
version: 1
created: 2026-04-22
author: swtman
notes: Initial zero-shot with ontology summary in the system prompt.
---

# System

...system prompt text...

# User (template)

...user prompt template, with {variables} for substitution...

# Notes

Design rationale, known failure modes, TODOs.
```

The loader reads the `# System` and `# User (template)` sections and does `.format(...)` on the user template with the variables you pass.

## Why this discipline matters

For the evaluation chapter of the thesis you will want to answer "did v2 actually do better than v1?" — that answer requires exact, reproducible prompt text tied to a version. Keeping them in version-controlled files (never in Python strings) gives you that for free.

## Current prompts

| Name | Latest version | Status |
|---|---|---|
| nl-to-sparql | v1 | Initial draft — not yet evaluated |
