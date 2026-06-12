# EvdoGraph ontology summary

> **STALE (2026-04-25 snapshot)** — this is the raw `explore_ontology.py` dump
> from before the supervisor's 2026-06-11 schema overhaul (old repo name
> `Evdoxus`, old Module/Course split, old counts). Kept for historical
> reference only. For the current schema, see `notes/ONTOLOGY-NOTES.md`; for
> the prompt-injected summary, see `prompts/ontology-summary.md`.

Endpoint: `http://lod.csd.auth.gr:7200/repositories/Evdoxus`

## Namespaces observed

- `http://www.w3.org/1999/02/22-rdf-syntax-ns#`
- `http://www.w3.org/2000/01/rdf-schema#`
- `http://www.w3.org/2002/07/owl#`
- `http://proton.semanticweb.org/protonsys#`
- `https://w3id.org/evdoxus#`
- `http://linkedscience.org/teach/ns#`
- `http://purl.org/vocab/aiiso/schema#`
- `https://schema.org/`
- `http://www.w3.org/2006/vcard/ns#`
- `http://xmlns.com/foaf/0.1/`
- `https://diuf.unifr.ch/xi/bowlogna/`
- `http://dbpedia.org/ontology/`
- `http://www.wikidata.org/entity/`
- `http://www.w3.org/ns/org#`
- `http://purl.org/ontology/bibo/`
- `http://vivoweb.org/ontology/core#`
- `https://w3id.org/nsk/`

## Top classes (by instance count)

| Class | Count | Sample labels |
|---|---:|---|
| `https://w3id.org/evdoxus#LearningEntity` | 585,188 | evdoxus#book_1000, evdoxus#book_10000, evdoxus#book_10002 |
| `https://w3id.org/evdoxus#Module` | 535,143 | evdoxus#module_1054_2010_1, evdoxus#module_1054_2010_10, evdoxus#module_1054_2010_11 |
| `http://linkedscience.org/teach/ns#Course` | 535,143 | evdoxus#module_1054_2010_1, evdoxus#module_1054_2010_10, evdoxus#module_1054_2010_11 |
| `http://purl.org/vocab/aiiso/schema#Course` | 535,143 | evdoxus#module_1054_2010_1, evdoxus#module_1054_2010_10, evdoxus#module_1054_2010_11 |
| `http://vivoweb.org/ontology/core#Course` | 535,143 | evdoxus#module_1054_2010_1, evdoxus#module_1054_2010_10, evdoxus#module_1054_2010_11 |
| `https://diuf.unifr.ch/xi/bowlogna/Module` | 535,143 | evdoxus#module_1054_2010_1, evdoxus#module_1054_2010_10, evdoxus#module_1054_2010_11 |
| `https://schema.org/Course` | 535,143 | evdoxus#module_1054_2010_1, evdoxus#module_1054_2010_10, evdoxus#module_1054_2010_11 |
| `http://www.wikidata.org/entity/Q600134` | 535,143 | evdoxus#module_1054_2010_1, evdoxus#module_1054_2010_10, evdoxus#module_1054_2010_11 |
| `https://w3id.org/evdoxus#Book` | 40,529 | evdoxus#book_1000, evdoxus#book_10000, evdoxus#book_10002 |
| `http://linkedscience.org/teach/ns#Material` | 40,529 | evdoxus#book_1000, evdoxus#book_10000, evdoxus#book_10002 |
| `http://dbpedia.org/ontology/Book` | 40,529 |  |
| `http://purl.org/ontology/bibo/Book` | 40,529 |  |
| `https://schema.org/Book` | 40,529 |  |
| `http://www.wikidata.org/entity/Q571` | 40,529 |  |
| `https://w3id.org/evdoxus#Course` | 9,516 |  |
| `https://schema.org/EducationalOccupationalProgram` | 9,516 |  |
| `http://linkedscience.org/teach/ns#StudyProgram` | 9,516 |  |
| `http://purl.org/vocab/aiiso/schema#Programme` | 9,516 |  |
| `https://diuf.unifr.ch/xi/bowlogna/Study_Program` | 9,516 |  |
| `http://www.wikidata.org/entity/Q207137` | 9,516 |  |
| `https://w3id.org/evdoxus#AcademicEntity` | 778 |  |
| `https://w3id.org/evdoxus#Department` | 732 |  |
| `https://schema.org/School` | 732 |  |
| `http://purl.org/vocab/aiiso/schema#Department` | 732 |  |
| `http://vivoweb.org/ontology/core#AcademicDepartment` | 732 |  |
| `https://diuf.unifr.ch/xi/bowlogna/Department` | 732 |  |
| `http://www.wikidata.org/entity/Q2467461` | 732 |  |
| `http://www.w3.org/ns/org#OrganizationalUnit` | 103 |  |
| `https://w3id.org/nsk/Bureau` | 80 |  |
| `https://w3id.org/nsk/GRAFEIA-NOMIKOY-SYMBOYLIOY-EIDIKA-GRAFEIA-NOMIKOY-SYMBOYLIOY` | 66 |  |
| `https://w3id.org/evdoxus#University` | 46 |  |
| `http://purl.org/vocab/aiiso/schema#Institution` | 46 |  |
| `https://schema.org/CollegeOrUniversity` | 46 |  |
| `http://dbpedia.org/ontology/University` | 46 |  |
| `http://vivoweb.org/ontology/core#University` | 46 |  |
| `http://www.wikidata.org/entity/Q3918` | 46 |  |
| `https://w3id.org/nsk/Department` | 12 |  |
| `https://w3id.org/nsk/Grafeia-Sximatismon` | 8 |  |
| `https://w3id.org/nsk/Formation` | 6 |  |
| `https://w3id.org/nsk/SXIMATISMOI-DIKASTIKON-KAI-EXODIKON-YPOTHESEON` | 4 |  |
| `https://w3id.org/nsk/Directorate` | 3 |  |
| `https://w3id.org/nsk/THEMATIKOI-SXIMATISMOI` | 3 |  |
| `https://w3id.org/nsk/Secretariat` | 1 |  |
| `https://w3id.org/nsk/Service` | 1 |  |
| `http://xmlns.com/foaf/0.1/Person` | 1 |  |
| `http://www.w3.org/ns/org#FormalOrganization` | 1 |  |

## Top properties (by usage count)

| Property | Count |
|---|---:|
| `https://w3id.org/evdoxus#hasBook` | 995,768 |
| `https://w3id.org/evdoxus#title` | 585,188 |
| `https://w3id.org/evdoxus#hasCode` | 576,404 |
| `https://w3id.org/evdoxus#semester` | 538,182 |
| `https://w3id.org/evdoxus#hasModule` | 535,143 |
| `https://w3id.org/evdoxus#hasURL` | 50,045 |
| `https://w3id.org/evdoxus#year` | 9,516 |
| `https://w3id.org/evdoxus#hasCourse` | 9,516 |
| `https://w3id.org/evdoxus#name` | 778 |
| `https://w3id.org/evdoxus#hasDepartment` | 732 |

## Suggested prompt-friendly schema

_(A compact version of the above, suitable for pasting into the `{ontology_summary}` slot in `prompts/nl-to-sparql-v1.md`. Hand-curate this after exploring.)_

```turtle
# TODO: fill in with the most useful ~20 classes and ~30 properties.
# Keep the whole section under ~2000 tokens.
```