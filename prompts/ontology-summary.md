PREFIX evdx: <https://w3id.org/evdoxus#>

Main classes:
- evdx:University   — a Greek university (46 unique instances)
- evdx:Department   — a department within a university (743); linked via evdx:hasDepartment
- evdx:Course       — a single course offering in a given year/semester (680,231); linked to dept via evdx:hasCourse
- evdx:Book         — a textbook (48,679); linked to course via evdx:hasBook
- evdx:Publisher    — a book publisher (1,698); linked to book via evdx:hasPublisher

Key properties (traversal):
- evdx:hasDepartment       University → Department  (inverse: evdx:belongsToUniversity)
- evdx:hasCourse           Department → Course      (inverse: evdx:isGivenByDepartment)
- evdx:hasBook             Course → Book             (inverse: evdx:proposedForCourse)
- evdx:hasPublisher        Book → Publisher          (inverse: evdx:publishes)

Key properties (literals):
- evdx:title           LearningEntity (Course or Book) → string
- evdx:name            AcademicEntity (Dept or University) → string
- evdx:semester        Course → integer (e.g. 6, unquoted — see IMPORTANT note below)
- evdx:year            Course → integer (e.g. 2021)
- evdx:professors      Course → string (professor name(s) teaching this offering)
- evdx:hasCode         LearningEntity → integer (Eudoxus internal code — NOT an ISBN; write as an unquoted number, e.g. VALUES ?code {94700120})
- evdx:hasURL          LearningEntity → URL
- evdx:authors         Book → string
- evdx:isbn            Book → string
- evdx:publicationYear Book → integer
- evdx:edition         Book → string
- evdx:keyword         Book → string (topic/subject tag; MULTI-VALUED — a book may have several evdx:keyword triples)
- evdx:publisherName   Publisher (or Book) → string

Other Book metadata (exists but rarely queried): evdx:bookType, evdx:coverType,
evdx:pages, evdx:bookSize, evdx:contents, evdx:excerpt, evdx:frontCover,
evdx:backCover, evdx:distributor, evdx:publisherWebPage.

NOT in the ontology:
- Student enrollment, grades, price.

IMPORTANT:
- evdx:Course is a single course offering ("μάθημα") in a specific year/semester
  — there is NO separate "study programme" class. Do not invent one.
- Departments share names across universities — group by University when
  querying Departments to avoid merging identically-named items.
- evdx:hasCode is the Eudoxus-internal code, distinct from evdx:isbn (the ISBN).
  It is an xsd:integer — use unquoted numbers (94700120, not "94700120").
- evdx:semester, evdx:year, and evdx:publicationYear are all xsd:integer —
  use unquoted numbers (?c evdx:semester 6, not "6"). A quoted string is a
  different RDF term from an integer and silently matches zero triples.
- evdx:hasSchool is a string literal on Department/University (a school NAME),
  NOT a link to a separate School class.
- A Department can have multiple evdx:belongsToUniversity parents (joint
  programmes) — use SELECT DISTINCT when traversing Department → University.
- Always prefer the evdx: namespace over aliases (teach:, schema:, aiiso:, etc.).
