# EvdoGraph ontology notes

_A living scratchpad. Major rewrite 2026-06-11 after the supervisor's KG/ontology
overhaul — the schema below supersedes the 2026-04-25 version (preserved in git
history). By the time you're writing thesis Chapter 02.5 (EvdoGraph), this file
should be a complete brain dump._

## Endpoint

- GraphDB root: `http://lod.csd.auth.gr:7200/`
- SPARQL endpoint (current): `http://lod.csd.auth.gr:7200/repositories/EvdoGraph`
  (renamed from `/repositories/Evdoxus` — same server, new repository name)
- Workbench UI: open the root URL in a browser for a visual explorer.
- **Status (2026-06-11):** endpoint is timing out on all queries, including
  `LIMIT`-bounded ones — likely still reindexing after the data load. The schema
  below is derived from `scripts/classes.json` + `scripts/properties.json`
  (manually exported by the supervisor/user), not live introspection. Re-run
  `scripts/explore_ontology.py` and the open-questions probes below once it
  recovers.

---

## ⚠️ MAJOR SCHEMA CHANGE (2026-06-11)

The previous version of this document described a 5-level hierarchy:
`University → Department → Course (study programme) → Module (course offering) → Book`.

**That hierarchy is GONE.** The new graph is flatter:

```
University ⇄ Department ⇄ Course ⇄ Book ⇄ Publisher
```

| Old name | Old meaning | New name | New meaning |
|---|---|---|---|
| `evdx:Module` (535,143) | a course **offering** (e.g. "Algorithms, autumn 2021") | **`evdx:Course`** (680,231) | now the course **offering** — old Module renamed |
| `evdx:Course` (9,516) | a study **programme** (e.g. "Computer Science BSc") | — **REMOVED** | the programme layer no longer exists |
| `evdx:LearningEntity` (585,188) | superclass for Book + Module | `evdx:LearningEntity` (728,910) | superclass for Book + Course (offering) |
| — | — | **`evdx:EvdoxusEntity`** (731,476) | new top superclass: LearningEntity ∪ Publisher ∪ AcademicEntity |
| — | — | **`evdx:Publisher`** (1,698) | new — publisher of a Book |

**Practical effect:** the old 4-hop traversal `Book → Module → Course(programme) →
Department → University` becomes a 3-hop traversal `Book → Course(offering) →
Department → University`. The "programme" indirection is simply removed — what
used to be `Department --hasCourse--> Course(programme) --hasModule--> Module`
is now directly `Department --hasCourse--> Course(offering)`.

**`evdx:Course` now means what users call a "course"/"μάθημα" (a single offering
in a given year/semester) — there is no remaining ambiguity with a "programme"
sense.** Update prompt Rule 12 accordingly (it currently teaches the OLD,
now-backwards distinction).

---

## Namespaces observed (2026-04-25 baseline; re-verify when endpoint recovers)

```turtle
@prefix rdf:    <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs:   <http://www.w3.org/2000/01/rdf-schema#> .
@prefix owl:    <http://www.w3.org/2002/07/owl#> .
@prefix evdx:   <https://w3id.org/evdoxus#> .          # PRIMARY namespace
@prefix teach:  <http://linkedscience.org/teach/ns#> .
@prefix aiiso:  <http://purl.org/vocab/aiiso/schema#> .
@prefix schema: <https://schema.org/> .
@prefix vcard:  <http://www.w3.org/2006/vcard/ns#> .
@prefix foaf:   <http://xmlns.com/foaf/0.1/> .
@prefix bowlogna: <https://diuf.unifr.ch/xi/bowlogna/> .
@prefix dbo:    <http://dbpedia.org/ontology/> .
@prefix wd:     <http://www.wikidata.org/entity/> .
@prefix org:    <http://www.w3.org/ns/org#> .
@prefix bibo:   <http://purl.org/ontology/bibo/> .
@prefix vivo:   <http://vivoweb.org/ontology/core#> .
@prefix nsk:    <https://w3id.org/nsk/> .
@prefix proton: <http://proton.semanticweb.org/protonsys#> .
@prefix spin:   <http://spinrdf.org/spin#> .            # NEW — observed 2026-06-11
```

> **Key takeaway (unchanged):** primary namespace is `https://w3id.org/evdoxus#`
> (prefix `evdx:`). Always prefer `evdx:` over the multiply-typed aliases.

---

## Classes (confirmed via `scripts/classes.json`, 2026-06-11)

| Class URI | Count | Notes |
|---|---:|---|
| `evdx:EvdoxusEntity` | 731,476 | **NEW** top superclass = LearningEntity ∪ Publisher ∪ AcademicEntity (728,910 + 1,698 + 868 = 731,476 ✓) |
| `evdx:LearningEntity` | 728,910 | Superclass for Book + Course (= 680,231 + 48,679 ✓) |
| `evdx:Course` | 680,231 | **A course offering** (renamed from old evdx:Module). Multiply typed: `teach:Course`, `aiiso:Course`, `vivo:Course`, `wd:Q600134`, `bowlogna:Module`, `schema:Course` — all same 680,231 instances |
| `evdx:Book` | 48,679 | A textbook. Multiply typed: `teach:Material`, `dbo:Book`, `bibo:Book`, `wd:Q571`, `schema:Book` |
| `evdx:Publisher` | 1,698 | **NEW** — a book publisher |
| `evdx:AcademicEntity` | 868 | Superclass for Department + University (= 743 + 125 ✓) |
| `evdx:Department` | 743 | A university department (was 732). Multiply typed: `schema:School`, `aiiso:Department`, `vivo:AcademicDepartment`, `wd:Q2467461`, `bowlogna:Department` |
| `evdx:University` | 125 | A university (was 46 — large jump, likely now includes more institution types; investigate) |

> **`evdx:Module` and the old `evdx:Course` (study programme, 9,516 instances) no
> longer appear at all** — confirms the programme layer was removed, not just renamed.

---

## Properties (confirmed via `scripts/properties.json`, 2026-06-11)

### Object properties (graph edges)

| Property | Direction | Notes |
|---|---|---|
| `evdx:hasDepartment` | University → Department | inverse of `belongsToUniversity` |
| `evdx:belongsToUniversity` | Department → University | inverse of `hasDepartment` |
| `evdx:hasCourse` | Department → Course | **replaces old Dept→Course(programme)→hasModule→Module chain** — now direct |
| `evdx:isGivenByDepartment` | Course → Department | inverse of `hasCourse` |
| `evdx:hasBook` | Course → Book | same name as before, now Course=offering is the subject |
| `evdx:proposedForCourse` | Book → Course | inverse of `hasBook` |
| `evdx:hasPublisher` | Book → Publisher | **NEW** |
| `evdx:publishes` | Publisher → Book | **NEW**, inverse of `hasPublisher` |

**New flat traversal path:** `University ⇄ Department ⇄ Course ⇄ Book ⇄ Publisher`

### Datatype properties (literals)

| Property | Likely domain | Notes |
|---|---|---|
| `evdx:title` | LearningEntity (Course or Book) | unchanged |
| `evdx:hasCode` | LearningEntity | Eudoxus internal code (NOT an ISBN) — unchanged |
| `evdx:hasURL` | LearningEntity | unchanged |
| `evdx:name` | AcademicEntity (Dept or University) | unchanged |
| `evdx:semester` | Course | unchanged |
| `evdx:year` | Course | **moved**: previously on the programme-level Course, now directly on the offering-level Course (count 680,231 == Course count, so every Course has a year) |
| `evdx:ID` | EvdoxusEntity (broad) | **NEW** — generic identifier, 731,484 ≈ EvdoxusEntity count |
| `evdx:secretaryID` | Department? | **NEW** — not yet sampled |
| `evdx:hasSchool` | Department or University | **NEW** — ⚠️ this is a `owl:DatatypeProperty` (a school-NAME literal), NOT a link to a separate School class. 704 uses for 743 depts |
| `evdx:professors` | Course | **NEW** — 518,275 uses; likely a literal string of professor name(s) per offering |
| `evdx:keyword` | Book | **NEW** — 111,700 uses; topic/subject tags on books — **directly relevant to the morphology/grounding problem** (topic-word matching against `keyword` may be more reliable than `title` substring matching) |
| `evdx:authors` | Book | **NEW** — 48,644 uses (≈ all books). Old summary said "NOT in ontology" — **now answerable** |
| `evdx:isbn` | Book | **NEW** — 47,460 uses. Old summary said "evdx:hasCode is NOT an ISBN, no ISBN property" — **now there IS one** |
| `evdx:publicationYear` | Book | **NEW** — 48,005 uses |
| `evdx:edition` | Book | **NEW** — 47,573 uses |
| `evdx:hasPublisher` / `evdx:publisherName` / `evdx:distributor` / `evdx:publisherWebPage` | Book / Publisher | **NEW** — publisher metadata, 1,698–48,679 uses |
| `evdx:bookType`, `evdx:coverType`, `evdx:pages`, `evdx:bookSize` | Book | **NEW** — physical book metadata, ~37k–48k uses |
| `evdx:contents`, `evdx:excerpt`, `evdx:frontCover`, `evdx:backCover` | Book | **NEW** — descriptive/media fields, ~38k–43k uses |

> **Old "NOT in the ontology" list is now WRONG.** ISBN, author, publisher, and
> price-adjacent metadata (edition, cover type, pages) are now all present. Only
> student enrollment/grades remain genuinely absent (no property suggests this).

---

## Open questions (probe live when endpoint recovers)

1. **`evdx:year` / `evdx:publicationYear` datatype** — integer or string? Affects
   `FILTER (?year >= 2019)` vs string comparison in examples.
2. **University count 46 → 125** — what are the extra 79 universities? Possibly
   includes institutions that were previously unmodeled (κολλέγια, ΙΕΚ?). Does
   `evdx:name` still uniquely identify them? Re-run `scripts/dump_labels.py`
   against the new endpoint to get the full list (gazetteer reseed, deferred).
3. **`belongsToUniversity`/`hasDepartment` count = 2,259** for 743 departments
   (~3.04 per dept) — multi-parent departments (joint programmes across
   universities?) or duplicate department nodes? Affects whether dedup is needed
   when traversing Dept→University.
4. **`evdx:hasSchool` literal samples** — 704 uses across 743 depts; what does a
   "school" name look like, and is it a useful grouping above Department?
5. **Sample literal shapes** for `keyword`, `professors`, `authors`, `semester` —
   single value vs comma/semicolon-delimited multi-value strings. This determines
   whether `CONTAINS()` substring matching works directly or needs splitting.
6. **Do the old example book codes still exist** (e.g. `94700120`, `102070469`,
   `13909`, `12867416`, `94700120`)? `evdx:hasCode` count (728,890) ≈ LearningEntity
   count (728,910), so the property survived — but specific values need
   re-verification before reusing them in rewritten gold examples.

---

## Interesting example queries

**STALE — all of `notes/draftedQueries.txt#Q1-Q18` and `prompts/examples.yaml`
predate this schema change and use `evdx:Module`/`evdx:hasModule`/the old
programme-level `evdx:Course`.** They are being rewritten against the new
flat topology (`prompts/examples.yaml`, tracked separately). The 2026-04-25
example queries (q1–q4, hand-written sanity tests) are preserved in git history
for reference but are no longer valid SPARQL against the current graph (they
reference `evdx:Module` and `evdx:hasModule`, neither of which exist anymore).

---

## Prompt-friendly schema summary

_(Compact version for the `{ontology_summary}` slot in `prompts/nl-to-sparql-v4.md`.
See `prompts/ontology-summary.md` for the canonical, hand-curated version — kept in
sync with this file.)_

```
PREFIX evdx: <https://w3id.org/evdoxus#>

Main classes:
- evdx:University   — a Greek university (125 instances)
- evdx:Department   — a dept within a university (743); linked via evdx:hasDepartment
- evdx:Course       — a single course offering in a year/semester (680,231); linked to dept via evdx:hasCourse
- evdx:Book         — a textbook (48,679); linked to course via evdx:hasBook
- evdx:Publisher    — a book publisher (1,698); linked to book via evdx:hasPublisher

Key properties:
- evdx:hasDepartment       University → Department
- evdx:hasCourse           Department → Course (a single offering, NOT a programme)
- evdx:hasBook             Course → Book
- evdx:hasPublisher        Book → Publisher
- evdx:title               LearningEntity (Course or Book) → string
- evdx:name                AcademicEntity (Dept or University) → string
- evdx:semester / evdx:year   Course → string/int
- evdx:hasCode             LearningEntity → string (Eudoxus code, NOT an ISBN)
- evdx:authors / evdx:isbn / evdx:publicationYear / evdx:edition  Book → string
- evdx:keyword             Book → string (topic tag — useful for topic search)
- evdx:professors          Course → string

IMPORTANT:
- evdx:Course IS a single course offering ("μάθημα") — there is NO separate
  "study programme" class anymore. Do not invent one.
- Departments may share names across universities — group by University when
  querying Departments.
- Always prefer the evdx: namespace over aliases (teach:, schema:, aiiso:, etc.).
```

---

## Thesis material harvested from this file

When writing thesis Chapter 02.5 (EvdoGraph):
- The mid-project schema overhaul itself is a useful narrative point — KGs built
  from evolving source data require the NLQ pipeline (prompts, examples, gazetteer)
  to be re-baselined, not just the application code.
- New statistics: 731k EvdoxusEntity, 680k Course offerings, 48.7k Books, 1,698
  Publishers, 743 Departments, 125 Universities.
- New book metadata (authors, ISBN, publisher, keyword) significantly expands the
  set of answerable questions — good "before/after" comparison material.
