PREFIX evdx: <https://w3id.org/evdoxus#>

Main classes:
- evdx:University   — a Greek university (46 instances)
- evdx:Department   — a department within a university (732); linked via evdx:hasDepartment
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
- evdx:year            Course → integer (e.g. 2021)
- evdx:hasCode         LearningEntity → string (Eudoxus book code)
- evdx:hasURL          LearningEntity → URL

IMPORTANT: evdx:Module is what people call a "course".
evdx:Course is a study programme (e.g. "Computer Science BSc") — NOT a single course.
Always prefer the evdx: namespace over aliases (teach:, schema:, aiiso:, etc.).
