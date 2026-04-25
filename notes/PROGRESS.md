# Progress log

_At the end of every coding session, append a new entry. Keep it short. This is what you read first when you sit back down._

## How to use this file

Each session = one H2 section. Three H3s: **Done**, **Next**, **Blockers/notes**. The next-session-you (or next Claude) reads the top entry and knows exactly what to pick up.

Template:

```markdown
## YYYY-MM-DD — <one-line summary of session focus>

### Done
- Bullet points of what was finished.

### Next
- What to do next session, in rough priority order.

### Blockers / notes
- Anything unresolved, weird, or worth remembering.
```

---

## 2026-04-25 — Backend pipeline complete

### Done
- Full backend pipeline implemented (16 tasks, all tests green).
- config.py, LLMProvider protocol, FakeProvider, ClaudeProvider (generate + stream), DiskCache.
- PromptLoader (strips frontmatter, extracts # System, safe SPARQL fill), OntologyLoader (static file, module-level cache).
- SparqlClient (rdflib offline validation + SPARQLWrapper execution), ProviderFactory.
- POST /query (sync JSON, retry logic, _clean_sparql, _is_not_answerable).
- POST /query/stream (SSE, token streaming, non-streaming retry, done event with token counts).
- GET /providers (static list for UI dropdown).
- prompts/nl-to-sparql-retry-v1.md, prompts/ontology-summary.md created.
- 33 non-live tests pass; 2 live tests available with `uv run pytest -m live`.
- git repo initialized at monorepo root; all commits on master.

### Next
1. Push to GitHub (create remote, `git push -u origin master`).
2. Run live tests: `uv run pytest -m live` (needs GraphDB up + ANTHROPIC_API_KEY in .env).
3. Start the frontend — React + Vite scaffold.
4. Build the React query hook using `fetch + ReadableStream` for POST /query/stream (see TODO in query.py).

### Blockers / notes
- Internship starts 2026-05-18 — frontend MVP must be stable before then.
- SSE transport: frontend must use `fetch + ReadableStream`, NOT `EventSource` (GET-only).
- GitHub remote not yet set up (gh CLI not installed; create repo at github.com then push manually).

---

## 2026-04-25 — GraphDB endpoint confirmed reachable

### Done
- Ran `scripts/sparql_hello.py` against `http://lod.csd.auth.gr:7200/repositories/Evdoxus`.
- Queries 1 (triple count) and 2 (top classes by instance count) passed — endpoint is up and returning data.

### Next
1. Run `scripts/explore_ontology.py` to dump classes/properties into `notes/ONTOLOGY-NOTES.md`.
2. Push the scaffolded repo to GitHub.

### Blockers / notes
- the endpoint itself is confirmed working.
- Remember: internship starts 2026-05-18; MVP needs to be stable before then.

---

## 2026-04-22 — Project scaffolded

### Done
- Decided stack: Python + FastAPI + rdflib, React + Vite + TS, GraphDB remote endpoint, pluggable LLM default to Claude Haiku.
- Scaffolded the full repo: CLAUDE.md files, decisions/, prompts/, notes/, scripts/.
- Wrote ADRs 001 (Python/FastAPI), 002 (pluggable LLM), 003 (remote GraphDB).

### Next
1. Install `uv` and `pnpm` locally if not already.
2. Run `scripts/sparql_hello.py` to confirm the GraphDB endpoint is reachable from your machine. **This is the first real check.** If this fails, everything after is blocked.
3. Figure out the exact repository path at `lod.csd.auth.gr:7200` — probably `/repositories/evdograph` but verify in GraphDB Workbench.
4. Run `scripts/explore_ontology.py` to dump the list of classes and properties into `notes/ONTOLOGY-NOTES.md`.
5. Push the scaffolded repo to GitHub.
6. Start Claude Code in the project folder and verify it picks up CLAUDE.md (`/status` should show it in context).

### Blockers / notes
- Haven't confirmed GraphDB repo path yet.
- Thesis format (LaTeX vs Markdown+Pandoc) still TBD.
- Internship starts 2026-05-18; plan to stabilise the MVP before then and shift to thesis-writing-heavy mode after.
