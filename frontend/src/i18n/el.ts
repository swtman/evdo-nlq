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

  /* ── Query form ──────────────────────────────────────────────────────── */
  searchPlaceholder: 'Ρωτήστε για βιβλία, πανεπιστήμια, μαθήματα...',
  searchButton:      'ΑΝΑΖΗΤΗΣΗ →',
  searching:         'ΑΝΑΖΗΤΗΣΗ...',
  providerLabel:     'πάροχος',
  modelLabel:        'μοντέλο',

  /* ── SPARQL panel ────────────────────────────────────────────────────── */
  sparqlLabel:      'SPARQL',
  sparqlGenerating: '// generating…',
  sparqlComplete:   '// ready',
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
  exportAllRows:  '// εξαγωγή όλων των γραμμών',
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
