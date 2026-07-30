/**
 * ontology.ts — hand-authored structured description of the EvdoGraph ontology.
 *
 * Source of truth for all structural blocks in OntologyPage and
 * EntitySpotlights: SchemaDiagram, class reference cards, relationships
 * table, example nodes (exampleNodes), and the small offline fallback
 * samples for the live course/book search cards (courseSearchStats /
 * SAMPLE_COURSE_TITLES, bookSearchStats / SAMPLE_BOOK_TITLES — the real,
 * ~73k/~37k title corpora live in backend/app/data/entities.db, not here;
 * see ADR-018/ADR-019).
 *
 * Instance counts from: notes/ONTOLOGY-NOTES.md (confirmed via live probe 2026-06-12).
 * Property info from: prompts/ontology-summary.md.
 * Snapshot date: 2026-06 (course search stats), 2026-07-31 (book search stats).
 */

export interface OntologyClass {
  /** Short CamelCase class name used in SPARQL (without prefix) */
  id: string
  /** English label */
  name: string
  /** Greek label shown in the diagram and cards */
  greek: string
  /** Number of instances in the KG (live snapshot 2026-06) */
  count: number
  /** Formatted count with Greek thousands separator (·) */
  countFormatted: string
  /** Ontology superclass this class belongs to */
  superclass: string
  /** One-sentence description for the class card */
  description: string
  /** Key datatype properties, shown as chips on the card */
  properties: string[]
  /** Example entity label shown on the card */
  example: string
}

export interface OntologySuperclass {
  id: string
  name: string
  /** Total instance count (sum of member classes) */
  count: number
  countFormatted: string
  /** IDs of member classes */
  members: string[]
  /** Visual style: 'solid' for main superclasses, 'dashed' for the top-level wrapper */
  style: 'solid' | 'dashed'
}

export interface Relationship {
  from: string
  property: string
  to: string
  inverse: string
}


// ── Generic example-node model (one real KG node per class) ──────────────────

/** How a single field value should be rendered in the example popup. */
export type ExampleFieldKind =
  | 'literal'   // plain string or number
  | 'ref'       // single evdx: reference — rendered in accent
  | 'refs'      // string[] of references — rendered as accent chips (first 3 + count)
  | 'link'      // URL — rendered as <a>; use `display` for the anchor text
  | 'keywords'  // string[] — rendered as keyword chips

export interface ExampleField {
  prop: string
  value: string | number | string[]
  /** Defaults to 'literal'. */
  kind?: ExampleFieldKind
  /** For 'link' fields — human-readable anchor label. Falls back to value. */
  display?: string
}

export interface ExampleNode {
  classId: string
  /** evdx:ID value */
  id: number
  /** Primary heading (evdx:name or evdx:title) */
  heading: string
  /** Optional context line under the heading — used for Course to clarify it is a single offering */
  subtitle?: string
  /** Cover image URL — only present for Book */
  image?: string
  fields: ExampleField[]
}

// ── Superclasses ─────────────────────────────────────────────────────────────

export const superclasses: OntologySuperclass[] = [
  {
    id: 'AcademicEntity',
    name: 'AcademicEntity',
    count: 868,
    countFormatted: '868',
    members: ['University', 'Department'],
    style: 'solid',
  },
  {
    id: 'LearningEntity',
    name: 'LearningEntity',
    count: 728910,
    countFormatted: '728.910',
    members: ['Course', 'Book'],
    style: 'solid',
  },
  {
    id: 'EvdoxusEntity',
    name: 'EvdoxusEntity',
    count: 731397,
    countFormatted: '731.397',
    members: ['University', 'Department', 'Course', 'Book', 'Publisher'],
    style: 'dashed',
  },
]

// ── Core classes ─────────────────────────────────────────────────────────────

export const classes: OntologyClass[] = [
  {
    id: 'University',
    name: 'University',
    greek: 'Πανεπιστήμιο',
    count: 46,
    countFormatted: '46',
    superclass: 'AcademicEntity',
    description:
      'Ελληνικό πανεπιστήμιο ή ΑΕΙ. Ορισμένα ιδρύματα φέρουν δύο ονόματα λόγω συγχώνευσης ή μετονομασίας.',
    properties: ['evdx:ID', 'evdx:name', 'evdx:hasDepartment →'],
    example: 'Αριστοτέλειο Πανεπιστήμιο Θεσσαλονίκης',
  },
  {
    id: 'Department',
    name: 'Department',
    greek: 'Τμήμα',
    count: 743,
    countFormatted: '743',
    superclass: 'AcademicEntity',
    description:
      'Τμήμα πανεπιστημίου. Το ίδιο όνομα τμήματος μπορεί να εμφανίζεται σε πολλά ιδρύματα.',
    properties: ['evdx:ID', 'evdx:name', 'evdx:hasCourse →', 'evdx:hasSchool', 'evdx:belongsToUniversity ←'],
    example: 'Τμήμα Πληροφορικής',
  },
  {
    id: 'Course',
    name: 'Course',
    greek: 'Μάθημα',
    count: 680231,
    countFormatted: '680.231',
    superclass: 'LearningEntity',
    description:
      'Μία προσφορά μαθήματος σε συγκεκριμένο εξάμηνο, έτος, τμήμα και πανεπιστήμιο. Πολλά μαθήματα έχουν το ίδιο όνομα, αλλά διαφορετικά έτη/εξάμηνα/τμήματα ή/και πανεπιστήμια.',
    properties: ['evdx:ID', 'evdx:hasCode', 'evdx:hasURL', 
      'evdx:title', 'evdx:year', 'evdx:isGivenByDepartment', 'evdx:semester', 
      'evdx:professors', 'evdx:hasBook →'],
    example: 'Αλγόριθμοι — εξ. 5, 2022',
  },
  {
    id: 'Book',
    name: 'Book',
    greek: 'Βιβλίο',
    count: 48679,
    countFormatted: '48.679',
    superclass: 'LearningEntity',
    description:
      'Διδακτικό σύγγραμμα προτεινόμενο για ένα ή περισσότερα μαθήματα. Διαθέτει ISBN, συγγραφείς, πληροφορίες για το είδος και το μέγεθος του βιβλίου, για την έκδοση,'
      + ' τον εκδότη, θεματικές λέξεις-κλειδιά, συνδέσμους για το εξώφυλλο, το οπισθόφυλλο, το περιεχόμενο, το απόσπασμα και την ιστοσελίδα του εκδότη.',
    properties: ['evdx:ID','evdx:authors','evdx:backCover','evdx:bookSize','evdx:bookType',
    'evdx:contents','evdx:coverType','evdx:distributor','evdx:edition','evdx:excerpt',
    'evdx:frontCover','evdx:hasCode','evdx:hasPublisher','evdx:hasURL','evdx:isbn',
    'evdx:keyword','evdx:pages','evdx:proposedForCourse','evdx:publicationYear',
    'evdx:publisherWebPage','evdx:title'],
    example:``
  } ,
  {
    id: 'Publisher',
    name: 'Publisher',
    greek: 'Εκδότης',
    count: 1698,
    countFormatted: '1.698',
    superclass: 'EvdoxusEntity',
    description:
      'Εκδοτικός οίκος που δημοσιεύει ένα ή περισσότερα βιβλία.',
    properties: ['evdx:ID', 'evdx:publisherName', 'evdx:publishes →'],
    example: 'Κλειδάριθμος',
  },
]

// ── Object-property relationships ─────────────────────────────────────────────

export const relationships: Relationship[] = [
  { from: 'University',  property: 'hasDepartment',      to: 'Department', inverse: 'belongsToUniversity' },
  { from: 'Department',  property: 'hasCourse',          to: 'Course',     inverse: 'isGivenByDepartment' },
  { from: 'Course',      property: 'hasBook',            to: 'Book',       inverse: 'proposedForCourse'   },
  { from: 'Book',        property: 'hasPublisher',       to: 'Publisher',  inverse: 'publishes'            },
]

// ── Totals (for the page stat line) ──────────────────────────────────────────

export const totals = {
  classes: 5,
  relationships: 4,
  entities: 731397,
  entitiesFormatted: '731.397',
  books: 48679,
  booksFormatted: '48.679',
  snapshot: '06/2026',
}

// ── Course search stats (for the ΟΝΤΟΛΟΓΙΑ course search card) ────────────────
//
// distinctTitles: count of distinct normalized course titles in
//   backend/app/data/entities.db (built by scripts/build_entity_db.py). Many
//   Course *instances* (see classes[Course].count = 680.231 above) share the
//   same title across different years/semesters/departments — distinctTitles
//   is how many different titles a search can actually find.
//
// Updated 2026-07-31 (72,949 -> 72,937): the entities.db rebuild that added
// book search also fixed a data-integrity bug in the course-cleaning code
// (see app/grounding/clean.py) and, as a side effect of the fix, started
// dropping the small number of titles containing a literal newline (38 of
// them) rather than silently collapsing the newline into a space. The count
// dropped slightly because of that new, deliberate drop reason — not because
// titles went missing from the KG.

export const courseSearchStats = {
  distinctTitles: 72937,
  distinctTitlesFormatted: '72.937',
  snapshot: '2026-07-31',
}

// Small set of real course titles (same 2026-06 snapshot), used only as an
// offline fallback for the course search card when the backend is
// unreachable — see EntitySpotlights.tsx. Not a substitute for live search;
// the card labels this state explicitly so it's never mistaken for a result.
export const SAMPLE_COURSE_TITLES: string[] = [
  'Αρχιτεκτονική Υπολογιστών',
  'Τεχνητή Νοημοσύνη',
  'Λειτουργικά Συστήματα',
  'Δίκτυα Υπολογιστών',
  'Γραμμική Άλγεβρα',
  'Εισαγωγή στον Προγραμματισμό (Python)',
  'Ψηφιακή Επεξεργασία Σημάτων',
]

// ── Book search stats (for the ΟΝΤΟΛΟΓΙΑ book search card) ────────────────────
//
// distinctTitles: count of distinct normalized book titles in
//   backend/app/data/entities.db, from the 2026-07-31 rebuild that added the
//   book corpus (scripts/build_entity_db.py). Many Book *instances* (see
//   classes[Book].count = 48.679 above) share the same title across
//   editions/printings — distinctTitles is how many different titles a
//   search can actually find.

export const bookSearchStats = {
  distinctTitles: 36947,
  distinctTitlesFormatted: '36.947',
  snapshot: '2026-07-31',
}

// Small set of real book titles (2026-07-31 snapshot), used only as an
// offline fallback for the book search card — same pattern as
// SAMPLE_COURSE_TITLES above.
export const SAMPLE_BOOK_TITLES: string[] = [
  'Τεχνητή Νοημοσύνη',
  'Βάσεις Δεδομένων (Τράπεζες Πληροφοριών)',
  'Δίκτυα Υπολογιστών',
  'Λειτουργικά συστήματα',
  'Γραμμική Άλγεβρα',
  'Αλγόριθμοι',
  'Ψηφιακή επεξεργασία σημάτων',
]

// ── Example nodes — one real KG node per class ───────────────────────────────
//
// University (evdx:university_8): AUTh — ID derived from URI suffix; name from
//   the dbpedia-el alias visible in the Department's belongsToUniversity links.
// Department (evdx:dept_1596): Τμήμα Πληροφορικής ΑΠΘ — live data 2026-06.
// Course (evdx:course_143602167): live data 2026-06.
// Book (evdx:book_94700120): live data 2026-06.
// Publisher (evdx:publisher_1298): live data 2026-06.

export const exampleNodes: Record<string, ExampleNode> = {
  University: {
    classId: 'University',
    id: 8,
    heading: 'ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣΣΑΛΟΝΙΚΗΣ',
    fields: [
      { prop: 'evdx:name', value: 'ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣΣΑΛΟΝΙΚΗΣ' },
      { prop: 'evdx:hasDepartment', value: ['evdx:dept_1596', '...', '...'], kind: 'refs' },
    ],
  },

  Department: {
    classId: 'Department',
    id: 1596,
    heading: 'ΠΛΗΡΟΦΟΡΙΚΗΣ',
    fields: [
      { prop: 'evdx:name', value: 'ΠΛΗΡΟΦΟΡΙΚΗΣ' },
      { prop: 'evdx:hasSchool', value: 'ΘΕΤΙΚΩΝ ΕΠΙΣΤΗΜΩΝ' },
      {
        prop: 'evdx:belongsToUniversity',
        value: ['evdx:university_8', 'dbpedia-el:Αριστοτέλειο_Πανεπιστήμιο_Θεσσαλονίκης', 'dbr:Aristotle_University_of_Thessaloniki'],
        kind: 'refs',
      },
      { prop: 'evdx:hasCourse', value: ['evdx:course_122206136', 'evdx:course_133136247', 'evdx:course_143602116', '...', '...'], kind: 'refs' },
    ],
  },

  Course: {
    classId: 'Course',
    id: 143602167,
    heading: 'ΥΠΟΛΟΓΙΣΤΙΚΗ ΛΟΓΙΚΗ ΚΑΙ ΛΟΓΙΚΟΣ ΠΡΟΓΡΑΜΜΑΤΙΣΜΟΣ',
    subtitle: 'στιγμιότυπο προσφοράς μαθήματος · 6ο εξάμηνο · 2025 · Τμήμα Πληροφορικής ΑΠΘ',
    fields: [
      { prop: 'evdx:title', value: 'ΥΠΟΛΟΓΙΣΤΙΚΗ ΛΟΓΙΚΗ ΚΑΙ ΛΟΓΙΚΟΣ ΠΡΟΓΡΑΜΜΑΤΙΣΜΟΣ' },
      { prop: 'evdx:hasCode', value: 'NIS-06-02' },
      { prop: 'evdx:year', value: 2025 },
      { prop: 'evdx:semester', value: 6 },
      { prop: 'evdx:professors', value: 'ΒΑΣΙΛΕΙΑΔΗΣ ΝΙΚΟΛΑΟΣ' },
      { prop: 'evdx:isGivenByDepartment', value: 'evdx:dept_1596', kind: 'ref' },
      { prop: 'evdx:hasBook', value: ['evdx:book_127532921', 'evdx:book_320042', 'evdx:book_5417', 'evdx:book_86200975'], kind: 'refs' },
      {
        prop: 'evdx:hasURL',
        value: 'https://service.eudoxus.gr/coursebooks/rest/courses-books/course/143602167/books',
        kind: 'link',
        display: 'eudoxus.gr · 143602167',
      },
    ],
  },

  Book: {
    classId: 'Book',
    id: 94700120,
    heading: 'ΤΕΧΝΗΤΗ ΝΟΗΜΟΣΥΝΗ - 4η ΕΚΔΟΣΗ',
    image: 'https://static.eudoxus.gr/books/20/cover-94700120.jpg',
    fields: [
      { prop: 'evdx:authors', value: 'ΒΛΑΧΑΒΑΣ Ι. / ΚΕΦΑΛΑΣ Π. / ΒΑΣΙΛΕΙΑΔΗΣ Ν. / ΚΟΚΚΟΡΑΣ Φ. / ΣΑΚΕΛΛΑΡΙΟΥ Η.' },
      { prop: 'evdx:isbn', value: '9786185196448' },
      { prop: 'evdx:edition', value: 4 },
      { prop: 'evdx:pages', value: 1000 },
      { prop: 'evdx:publicationYear', value: 2020 },
      { prop: 'evdx:bookType', value: 'Published' },
      { prop: 'evdx:bookSize', value: '[17 x 24]' },
      { prop: 'evdx:coverType', value: 'Soft' },
      {
        prop: 'evdx:keyword',
        value: ['πληροφοριακά συστήματα', 'υπολογιστές', 'τεχνητη νοημοσυνη',
          'υπολογιστική νοημοσύνη', 'πληροφορικά συστήματα',
          'εφαρμογες στην πληροφορική', 'εφαρμογες υπολογιστων', 'πληροφορικη'],
        kind: 'keywords',
      },
      { prop: 'evdx:hasPublisher', value: 'evdx:publisher_1441', kind: 'ref' },
      { prop: 'evdx:distributor', value: 'ΕΤΑΙΡΕΙΑ ΑΞΙΟΠΟΙΗΣΗΣ ΚΑΙ ΔΙΑΧΕΙΡΙΣΗΣ ΠΕΡΙΟΥΣΙΑΣ ΠΑΝΕΠΙΣΤΗΜΙΟΥ ΜΑΚΕΔΟΝΙΑΣ' },
      { prop: 'evdx:publisherWebPage', value: 'http://www.uompress.gr', kind: 'link', display: 'uompress.gr' },
      {
        prop: 'evdx:hasURL',
        value: 'https://service.eudoxus.gr/coursebooks/rest/courses-books/book/eudoxus/info?bookId=94700120',
        kind: 'link',
        display: 'eudoxus.gr · 94700120',
      },
      { prop: 'evdx:frontCover', value: 'https://static.eudoxus.gr/books/20/cover-94700120.jpg', kind: 'link', display: 'cover-94700120.jpg' },
      { prop: 'evdx:backCover', value: 'https://static.eudoxus.gr/books/20/backcover-94700120.jpg', kind: 'link', display: 'backcover-94700120.jpg' },
      { prop: 'evdx:contents', value: 'https://static.eudoxus.gr/books/20/toc-94700120.pdf', kind: 'link', display: 'toc-94700120.pdf' },
      { prop: 'evdx:excerpt', value: 'https://static.eudoxus.gr/books/20/chapter-94700120.pdf', kind: 'link', display: 'chapter-94700120.pdf' },
      { prop: 'evdx:proposedForCourse', value: 'evdx:course_102148977', kind: 'ref' },
    ],
  },

  Publisher: {
    classId: 'Publisher',
    id: 1298,
    heading: 'ΕΚΔΟΣΕΙΣ ΚΛΕΙΔΑΡΙΘΜΟΣ ΕΠΕ',
    fields: [
      { prop: 'evdx:publisherName', value: 'ΕΚΔΟΣΕΙΣ ΚΛΕΙΔΑΡΙΘΜΟΣ ΕΠΕ' },
      { prop: 'evdx:publishes', value: ['evdx:book_102070435', 'evdx:book_102070437', 'evdx:book_102070439', '...', '...'], kind: 'refs' },
    ],
  },
}
