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
    'Βιβλία στο ΑΠΘ',
    'Μαθήματα Πληροφορικής',
  ],

  /* ── Question echo (above SPARQL panel) ──────────────────────────────── */
  questionEchoLabel: 'ΕΡΩΤΗΣΗ',

  /* ── SPARQL terminal chrome ──────────────────────────────────────────── */
  sparqlFilename: 'query.sparql',
  sparqlReady:    'έτοιμο',

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
  noResultsBody:   'καμία αντιστοίχιση. δοκίμασε να αναδιατυπώσεις:',
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
  ontologySectionClasses:  'Κλάσεις',
  ontologySectionRels:     'Σχέσεις',
  ontologySectionEntities: 'Οντότητες',

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
  ontologySpotDeptSub:   (n: number): string => `743 διαφορετικά τμήματα · ${n} μοναδικά ονόματα τμημάτων`,
  ontologySpotBookTitle: 'Βιβλία',
  ontologySpotBookSub:   (distinctTitles: string, totalInstances: string): string =>
    `${distinctTitles} μοναδικοί τίτλοι · ${totalInstances} συνολικά βιβλία`,
  ontologyBookSearchPlaceholder: 'αναζήτηση βιβλίου… π.χ. τεχνητή νοημοσύνη',
  ontologyBookOffline: 'χωρίς σύνδεση με τον διακομιστή — δείγμα τίτλων',
  ontologyBookNoResults: 'καμία αντιστοίχιση',
  ontologySpotCourseTitle: 'Μαθήματα',
  ontologySpotCourseSub:   (distinctTitles: string, totalInstances: string): string =>
    `${distinctTitles} μοναδικοί τίτλοι · ${totalInstances} συνολικές προσφορές μαθημάτων`,
  ontologyCourseSearchPlaceholder: 'αναζήτηση μαθήματος… π.χ. αρχιτεκτονική υπολογιστών',
  ontologySearching:   'αναζήτηση…',
  ontologyCourseOffline: 'χωρίς σύνδεση με τον διακομιστή — δείγμα τίτλων',
  ontologyCourseNoResults: 'καμία αντιστοίχιση',

  ontologySearchPlaceholder: 'φιλτράρισμα…',
  ontologyShowMore: (n: number): string => `+ ${n} ακόμη`,
  ontologySeeAll: (n: number): string => `δείτε τα όλα (${n})`,
  ontologyModalClose: 'κλείσιμο',
  ontologyModalResults: (n: number): string => `${n} αποτελέσματα`,
  ontologyBookExampleBtn: 'δείτε παράδειγμα',
  ontologyExampleTitle: (cls: string): string => `Παράδειγμα οντότητας ${cls}`,
  ontologyDeptSharedNote: (n: number): string => `${n} ιδρύματα`,
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
