/**
 * All user-visible strings in the application, in Greek.
 *
 * Usage in any component:
 *   import { t } from '../i18n/el'
 *   <button>{t.searchButton}</button>
 *
 * Some keys are functions that accept runtime values and return a formatted string:
 *   t.pageInfo(2, 5)          → "σελίδα 2 από 5"
 *   t.historyMobileToggle(3)  → "≡ ιστορικό (3)"
 *
 * To add English support, create src/i18n/en.ts with the same shape and swap
 * the import, or select the object at runtime based on a locale variable.
 */
export const t = {
  /* ── App header ──────────────────────────────────────────────────────── */
  title:        'EvdoGraph',
  titleAccent:  'NLQ',
  subtitle:     'Φυσική γλώσσα → SPARQL → Αποτελέσματα',
  switchToLight: 'Εναλλαγή σε φωτεινό θέμα',
  switchToDark:  'Εναλλαγή σε σκοτεινό θέμα',

  /* ── Console layout — topbar tabs ────────────────────────────────────── */
  tabQuery:    'ΕΡΩΤΗΜΑ',
  tabOntology: 'ΟΝΤΟΛΟΓΙΑ',
  tabHistory:  'ΙΣΤΟΡΙΚΟ',

  /* ── Hero section ────────────────────────────────────────────────────── */
  heroEyebrow: 'ΦΥΣΙΚΗ ΓΛΩΣΣΑ · SPARQL · ΑΠΟΤΕΛΕΣΜΑΤΑ',
  heroTitle:   'Τι θέλετε να μάθετε;',
  heroTryLabel: 'δοκιμάστε',
  heroChips: [
    'Πανεπιστήμια στην Ελλάδα',
    'Μαθήματα Πληροφορικής στο ΑΠΘ',
    'Βιβλία στο μάθημα "Τεχνητή Νοημοσύνη" στο τμήμα Πληροφορικής του ΑΠΘ',
  ],

  /* ── Question echo (above SPARQL panel) ──────────────────────────────── */
  questionEchoLabel: 'ΕΡΩΤΗΣΗ',

  /* ── SPARQL terminal chrome ──────────────────────────────────────────── */
  sparqlFilename: 'query.sparql',
  sparqlReady:    'έτοιμο',
  sparqlFailed:   'απέτυχε',

  /* ── Status bar ──────────────────────────────────────────────────────── */
  graphdbConnected: 'graphdb συνδεδεμένο',

  /* ── History drawer filter chips ─────────────────────────────────────── */
  historyFilterAll:     'όλα',
  historyFilterSuccess: 'επιτυχία',
  historyFilterError:   'σφάλμα',

  /* ── Query form ──────────────────────────────────────────────────────── */
  searchPlaceholder: 'Ρωτήστε για βιβλία, πανεπιστήμια, μαθήματα...',
  searchButton:      'ΑΝΑΖΗΤΗΣΗ →',
  searching:         'ΑΝΑΖΗΤΗΣΗ...',
  providerLabel:     'πάροχος',
  modelLabel:        'μοντέλο',

  /* ── SPARQL panel ────────────────────────────────────────────────────── */
  sparqlLabel:      'SPARQL',
  sparqlGenerating: '// generating…',
  sparqlComplete:   'ready',
  sparqlCopy:       '⧉ αντιγραφή',
  sparqlCopied:     '✓ αντιγράφηκε',
  sparqlEdit:       '✎ επεξεργασία',
  sparqlCancel:     '✕ ακύρωση',
  sparqlRerun:      '⟳ επανεκτέλεση',
  sparqlHide:       '▼ απόκρυψη',
  sparqlShow:       '▶ εμφάνιση',
  sparqlCollapse:   '▼',
  sparqlExpand:     '▶',
  graphdbExecuting: 'graphdb · εκτέλεση…',

  /* ── Results panel ───────────────────────────────────────────────────── */
  resultsLabel:   'Αποτελέσματα',
  columnsLabel:   '⊞ στήλες',
  exportLabel:    '↓ εξαγωγή ▾',
  exportAllRows:  'εξαγωγή των αποτελεσμάτων σε αρχείο',
  exportCsv:      'CSV',
  exportCsvDesc:  'comma-separated',
  exportJson:     'JSON',
  exportJsonDesc: 'structured',
  exportXml:      'XML',
  exportXmlDesc:  'SPARQL XML',
  exportTsv:      'TSV',
  exportTsvDesc:  'tab-separated',

  tokenInfo: (input: number, output: number, retries: number): string =>
    `${input} input · ${output} output tokens${retries > 0 ? ` · ${retries} retries` : ''}`,

  resultsCountLabel: (n: number): string => `${n}`,
  resultsMeta: (graphdbMs: number, llmS: number, retries: number): string =>
    `graphdb ${graphdbMs}ms · llm ${llmS.toFixed(1)}s${retries > 0 ? ` · ${retries} retries` : ''}`,

  cachedBadge: '(αποθηκευμένο)',
  historyManualEdit: '✎ (edited)',

  /* ── Pagination ──────────────────────────────────────────────────────── */
  pageRowsLabel: 'γραμμές:',
  pagePrev:      '← προηγ.',
  pageNext:      'επόμ. →',
  pageInfo: (p: number, total: number): string => `σελίδα ${p} από ${total}`,

  /* ── Empty state ─────────────────────────────────────────────────────── */
  noResults:       'Δεν βρέθηκαν αποτελέσματα.',
  noResultsTitle:  '// 0 αποτελέσματα',
  noResultsBody:   'κανένα αποτέλεσμα · δοκίμασε να αναδιατυπώσεις την ερώτησή σου',
  noResultsExamples: [
    'Ποια πανεπιστήμια υπάρχουν στην Ελλάδα;',
    'Βιβλία που χρησιμοποιούνται στο ΑΠΘ',
    'Μαθήματα Πληροφορικής στο ΑΠΘ',
  ],

  /* ── Ontology page ──────────────────────────────────────────────────── */
  ontologyEyebrow:     'ΓΡΑΦΟΣ ΟΝΤΟΛΟΓΙΑΣ',
  ontologyTitle:       'Η δομή του EvdoGraph',
  ontologyLead:        'Πώς οργανώνονται τα δεδομένα του Ευδόξου. Οι κλάσεις, οι ιδιότητες και οι σχέσεις που συνδέουν πανεπιστήμια, μαθήματα και βιβλία.',
  ontologyStatClasses: (n: number): string => `${n} κλάσεις`,
  ontologyStatRels:    (n: number): string => `${n} σχέσεις`,
  ontologyStatEntities:(n: string): string => `${n} οντότητες`,
  ontologyStatBooks:   (n: string): string => `${n} βιβλία`,

  ontologySectionDiagram:  'Διάγραμμα σχήματος',
  ontologySectionDiagramDesc: 'Πώς οργανώνονται τα δεδομένα του Ευδόξου',
  ontologySectionClasses:  'Κλάσεις',
  ontologySectionClassesDesc: 'Οι κλάσεις που αντιπροσωπεύουν τις κατηγορίες των οντοτήτων',
  ontologySectionRels:     'Σχέσεις',
  ontologySectionRelsDesc: 'Οι σχέσεις που συνδέουν τις οντότητες μεταξύ τους',
  ontologySectionEntities: 'Οντότητες',
  ontologySectionEntitiesDesc: 'Οι οντότητες που αντιπροσωπεύουν τα στοιχεία του γράφου',

  ontologyDiagramCaption: (snapshot: string): string => `στιγμιότυπο ${snapshot}`,
  ontologyDiagramLegend1: 'σχέση (με αντίστροφη)',
  ontologyDiagramLegend2: 'πλαίσιο = υπερκλάση',
  ontologyDiagramLegend3: 'count = πλήθος στιγμιοτύπων',

  ontologyRelFrom:    'Από',
  ontologyRelProp:    'Σχέση',
  ontologyRelTo:      'Προς',
  ontologyRelInverse: 'Αντίστροφη',

  ontologySpotUniTitle: 'Πανεπιστήμια',
  ontologySpotUniSub:   (n: number, total: number): string =>
    `${n} με καταχωρημένο όνομα · ${total} συνολικά`,
  ontologySpotDeptTitle: 'Τμήματα',
  // total = RDF Department instance count (classes[].count); n = distinct
  // department NAMES after deduplicating across universities (both passed
  // in by the caller — see departmentSearchStats in data/ontology.ts —
  // rather than one of them being baked into this template).
  ontologySpotDeptSub:   (total: number, n: number): string =>
    `${total} διαφορετικά τμήματα · ${n} μοναδικά ονόματα τμημάτων`,
  ontologySpotBookTitle: 'Βιβλία',
  ontologySpotBookSub:   (distinctTitles: string, totalInstances: string): string =>
    `${distinctTitles} μοναδικοί τίτλοι · ${totalInstances} συνολικά βιβλία`,
  ontologyBookSearchPlaceholder: 'αναζήτηση βιβλίου… π.χ. τεχνητή νοημοσύνη',
  // Shown before any query is typed — distinct from "no results", which only
  // applies once a search has actually run and come back empty. Shared by
  // all four live-search cards (course/book/university/department), and by
  // ontologyOffline/ontologyNoResults below — see ontologySearching, reused
  // the same way.
  ontologySearchPrompt: 'πληκτρολογήστε για αναζήτηση…',
  // Shared "no live backend" and "search ran, found nothing" labels — used
  // to be four near-duplicate pairs (ontologyCourseOffline/BookOffline/...),
  // byte-identical strings per class. One pair, since the message never
  // actually depended on which class was being searched.
  ontologyOffline: 'χωρίς σύνδεση με τον διακομιστή — δείγμα τίτλων',
  ontologyNoResults: 'κανένα αποτέλεσμα',
  ontologySpotCourseTitle: 'Μαθήματα',
  ontologySpotCourseSub:   (distinctTitles: string, totalInstances: string): string =>
    `${distinctTitles} μοναδικοί τίτλοι · ${totalInstances} συνολικές προσφορές μαθημάτων`,
  ontologyCourseSearchPlaceholder: 'αναζήτηση μαθήματος… π.χ. αρχιτεκτονική υπολογιστών',
  ontologySearching:   'αναζήτηση…',

  ontologyUniSearchPlaceholder: 'αναζήτηση πανεπιστημίου… π.χ. ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ',
  ontologyDeptSearchPlaceholder: 'αναζήτηση τμήματος… π.χ. ΠΛΗΡΟΦΟΡΙΚΗΣ',
  ontologyShowMore: (n: number): string => `+ ${n} ακόμη`,
  ontologySeeAll: (n: number): string => `δείτε τα όλα (${n})`,
  ontologyModalClose: 'κλείσιμο',
  ontologyModalResults: (n: number): string => `${n} αποτελέσματα`,
  ontologyBookExampleBtn: 'δείτε παράδειγμα',
  ontologyExampleTitle: (cls: string): string => `Παράδειγμα οντότητας ${cls}`,
  ontologyDeptSharedNote: (n: number): string => `${n} ιδρύματα`,
  // Label prefixing the parent-university list on a department row inside
  // the "δείτε τα όλα" browse modal (e.g. "Ιδρύματα: ΑΠΘ, ΠΑΝΕΠΙΣΤΗΜΙΟ
  // ΠΕΙΡΑΙΩΣ") — the inline search card only shows the ontologyDeptSharedNote
  // count badge; the modal has room to name them.
  ontologyDeptParentsLabel: 'Ιδρύματα',
  ontologyBookCode: 'κωδικός',
  ontologyBookAuthors: 'συγγραφείς',
  ontologyBookIsbn: 'isbn',
  ontologyBookKeywords: 'λέξεις-κλειδιά',
  ontologyBookPublisher: 'εκδότης',

  /* ── Error banner ────────────────────────────────────────────────────── */
  errorPrefix:      '// σφάλμα:',
  errorDismiss:     '[✕]',
  errorDismissLabel: 'Κλείσιμο ειδοποίησης',

  /* ── Sidebar ─────────────────────────────────────────────────────────── */
  historyLabel:            '// πρόσφατα ερωτήματα',
  historySearchPlaceholder: 'αναζήτηση ιστορικού…',
  historyClear:            'εκκαθάριση ιστορικού',
  historyEmpty:            'κανένα προηγούμενο ερώτημα',
  historyError:            'σφάλμα',
  historyMobileToggle: (n: number): string => `≡ ιστορικό (${n})`,
}
