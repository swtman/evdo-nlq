# EvdoGraph ontology notes

_A living scratchpad. Updated from `scripts/explore_ontology.py` output (2026-04-25). By the time you're writing thesis Chapter 02.5 (EvdoGraph), this file should be a complete brain dump._

## Endpoint

- GraphDB root: `http://lod.csd.auth.gr:7200/`
- SPARQL endpoint (confirmed): `http://lod.csd.auth.gr:7200/repositories/Evdoxus`
- Workbench UI: open the root URL in a browser for a visual explorer.

---

## Namespaces and prefixes

Confirmed namespaces observed in the store:

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
```

> **Key takeaway:** The primary namespace is `https://w3id.org/evdoxus#` (prefix `evdx:`). The ontology also reuses several well-known vocabularies (schema.org, teach, aiiso, bibo, foaf, vivo) — many classes are multiply typed using these.

---

## Classes (confirmed, by instance count)

| Class URI | Count | Notes |
|---|---:|---|
| `evdx:LearningEntity` | 585,188 | Superclass — covers both books and modules |
| `evdx:Module` | 535,143 | A course offering in a specific year; same URIs as teach:Course etc. |
| `teach:Course` | 535,143 | Same instances as evdx:Module (multiple types) |
| `aiiso:Course` | 535,143 | ↑ same |
| `vivo:Course` | 535,143 | ↑ same |
| `bowlogna:Module` | 535,143 | ↑ same |
| `schema:Course` | 535,143 | ↑ same |
| `wd:Q600134` | 535,143 | ↑ same |
| `evdx:Book` | 40,529 | A textbook |
| `teach:Material` | 40,529 | Same instances as evdx:Book |
| `dbo:Book` | 40,529 | ↑ same |
| `bibo:Book` | 40,529 | ↑ same |
| `schema:Book` | 40,529 | ↑ same |
| `wd:Q571` | 40,529 | ↑ same |
| `evdx:Course` | 9,516 | A study programme (not a module!) |
| `schema:EducationalOccupationalProgram` | 9,516 | Same as evdx:Course |
| `teach:StudyProgram` | 9,516 | ↑ same |
| `evdx:AcademicEntity` | 778 | Superclass for departments + universities |
| `evdx:Department` | 732 | A university department |
| `schema:School` | 732 | Same as evdx:Department |
| `evdx:University` | 46 | A university |
| `schema:CollegeOrUniversity` | 46 | Same as evdx:University |
| `foaf:Person` | 1 | Only 1 instance — authors are likely not modelled as persons |

> **Important naming confusion:** `evdx:Course` (9,516) = a **study programme** (e.g. "Computer Science BSc"). `evdx:Module` (535,143) = a **course offering** (e.g. "Algorithms, autumn 2021"). Keep this straight in prompts and queries.

---

## Key properties (confirmed, by usage count)

| Property | Count | Notes |
|---|---:|---|
| `evdx:hasBook` | 995,768 | Links Module → Book (many books per module) |
| `evdx:title` | 585,188 | Title of a LearningEntity (book or module) |
| `evdx:hasCode` | 576,404 | Code string on a LearningEntity |
| `evdx:semester` | 538,182 | Semester of a module |
| `evdx:hasModule` | 535,143 | Links Course (study programme) → Module |
| `evdx:hasURL` | 50,045 | URL (likely to Evdoxus website) |
| `evdx:year` | 9,516 | Academic year of a Course (study programme) |
| `evdx:hasCourse` | 9,516 | Links Department → Course (study programme) |
| `evdx:name` | 778 | Name of an AcademicEntity (department/university) |
| `evdx:hasDepartment` | 732 | Links University → Department |

> **Note:** No author-related properties appear in the top properties. Authors are likely stored as literal strings on books (possibly `evdx:title` contains author info, or there's a property not in the top-10). Needs further investigation.

---

## Interesting example queries (hand-written for sanity testing)

```sparql
# q1 - Return all modules that the book is used, along with the Department and the University

 PREFIX evdx: <https://w3id.org/evdoxus#>
 select (?un as ?University) (?dn as ?Department) (?mt as ?Module) 
 where { 
 	?s a evdx:Book .
 	VALUES ?code {"94700120"}
 	?s evdx:hasCode ?code .
 	?m a evdx:Module .
 	?m evdx:title ?mt .
 	?m evdx:hasBook ?s .
 	?c a evdx:Course .
 	?c evdx:year 2022 .
 	?c evdx:hasModule ?m .
 	?d a evdx:Department .
 	?d evdx:hasCourse ?c .
 	?d evdx:name ?dn .
 	?u a evdx:University .
 	?u evdx:hasDepartment ?d .
 	?u evdx:name ?un .
 }
Inside VALUES multiple book IDs can be used (e.g. various editions of the same book).
```

```sparql
# q2 - Return how many modules and all module names (in a string), that the book is used, along with the Department and the University, group by Department

 PREFIX evdx: <https://w3id.org/evdoxus#>
 select (?un as ?University) (?dn as ?Department)  (count(?m) as ?NoOfModules) (group_concat(?mt;separator=", ") as ?Modules) 
 where {
 	?m evdx:title ?mt .
 	{
 		select DISTINCT ?un ?dn ?m 
 		where { 
 			?s a evdx:Book .
 			VALUES ?code { "102070469" "13909" }
 			?s evdx:hasCode ?code .
 			?m a evdx:Module .
 			?m evdx:hasBook ?s .
 			?c a evdx:Course .
 			?c evdx:year 2022 .
 			?c evdx:hasModule ?m .
 			?d a evdx:Department .
 			?d evdx:hasCourse ?c .
 			?d evdx:name ?dn .
 			?u a evdx:University .
 			?u evdx:hasDepartment ?d .
 			?u evdx:name ?un .
 		}
 	}
 } group by ?un ?dn
```

```sparql
# q3 - Return in how many modules, of how many Departments and how many Universities the book is used

 PREFIX evdx: <https://w3id.org/evdoxus#>
 select (count(DISTINCT ?u) as ?Universities) (count(DISTINCT ?d) as ?Departments) (count(DISTINCT ?m) as ?NoOfModules) 
 where { 
 	?s a evdx:Book .
 	VALUES ?code { "102070469" "13909" }
 	?s evdx:hasCode ?code .
 	?m a evdx:Module .
 	?m evdx:hasBook ?s .
 	?c a evdx:Course .
 	?c evdx:year 2022 .
 	?c evdx:hasModule ?m .
 	?d a evdx:Department .
 	?d evdx:hasCourse ?c .
 	?u a evdx:University .
 	?u evdx:hasDepartment ?d .
 }
```
```sparql
# q4 - Return in how many modules, of how many Departments and how many Universities the book is used, per year, for a range of years

 PREFIX evdx: <https://w3id.org/evdoxus#>
 select ?year (count(DISTINCT ?u) as ?Universities) (count(DISTINCT ?d) as ?Departments) (count(DISTINCT ?m) as ?NoOfModules) 
 where { 
 	?s a evdx:Book .
 	VALUES ?code { "94700120" "12867416" }
 	?s evdx:hasCode ?code .
 	?m a evdx:Module .
 	?m evdx:hasBook ?s .
 	?c a evdx:Course .
 	?c evdx:year ?year.
 	FILTER ((?year>=2019) && (?year<2023)) .
 	?c evdx:hasModule ?m .
 	?d a evdx:Department .
 	?d evdx:hasCourse ?c .
 	?u a evdx:University .
 	?u evdx:hasDepartment ?d .
 } group by ?year
   order by ?year
   ```


---

## Gotchas / surprises found during exploration

- **Multiple typing is pervasive.** Every Module instance has 7+ types (evdx:Module, teach:Course, aiiso:Course, etc.). Always use the `evdx:` namespace in queries — it's the native one and avoids ambiguity.
- **`evdx:Course` ≠ a course.** It's actually a study programme. The thing most people call a "course" is `evdx:Module`. This will be a common source of LLM confusion — the prompt must make this explicit.
- **Authors are missing from the top properties.** With only 1 `foaf:Person` instance, author information is either stored as a literal or not modelled at all. Needs a targeted SPARQL query to find it.
- **`evdx:hasBook` count (995k) > `evdx:LearningEntity` count (585k).** This means books appear in many modules — the relationship is many-to-many.

---

## Prompt-friendly schema summary

_(Compact version for the `{ontology_summary}` slot in `prompts/nl-to-sparql-v1.md`. Under ~2000 tokens.)_

```
PREFIX evdx: <https://w3id.org/evdoxus#>

Main classes:
- evdx:University   — a Greek university (46 instances)
- evdx:Department   — a dept within a university (732); linked via evdx:hasDepartment
- evdx:Course       — a study programme / curriculum (9,516); linked to dept via evdx:hasCourse
- evdx:Module       — a single course offering in a year/semester (535,143); linked to programme via evdx:hasModule
- evdx:Book         — a textbook (40,529); linked to module via evdx:hasBook

Key properties:
- evdx:hasDepartment   University → Department
- evdx:hasCourse       Department → Course (study programme)
- evdx:hasModule       Course → Module (course offering)
- evdx:hasBook         Module → Book
- evdx:title           LearningEntity (Book or Module) → string
- evdx:name            AcademicEntity (Dept or University) → string
- evdx:semester        Module → string (e.g. "1", "2")
- evdx:year            Course → string (e.g. "2021")
- evdx:hasCode         LearningEntity → string (code identifier)
- evdx:hasURL          LearningEntity → URL

IMPORTANT: evdx:Module is what people call a "course". evdx:Course is a study programme (e.g. "Computer Science BSc").
```

---

## Thesis material harvested from this file

When writing thesis Chapter 02.5 (EvdoGraph), pull from:
- The namespaces table → Section "Schema overview" (note the multi-vocabulary alignment strategy).
- Classes and counts → Statistics paragraph (585k learning entities, 535k modules, 40k books, 46 universities).
- The Course/Module naming confusion → great example of ontology design challenges.
- Example queries → illustrate the richness of the data.
