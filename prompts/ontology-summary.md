PREFIX evdx: <https://w3id.org/evdoxus#>

Main classes:
- evdx:University   — a Greek university (125 instances)
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
- evdx:semester        Course → string (e.g. "1", "2")
- evdx:year            Course → integer (e.g. 2021)
- evdx:professors      Course → string (professor name(s) teaching this offering)
- evdx:hasCode         LearningEntity → string (Eudoxus internal code — NOT an ISBN)
- evdx:hasURL          LearningEntity → URL
- evdx:authors         Book → string
- evdx:isbn            Book → string
- evdx:publicationYear Book → integer
- evdx:edition         Book → string
- evdx:keyword         Book → string (topic/subject tag — useful for topic searches)
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
- evdx:hasSchool is a string literal on Department/University (a school NAME),
  NOT a link to a separate School class.
- Always prefer the evdx: namespace over aliases (teach:, schema:, aiiso:, etc.).
