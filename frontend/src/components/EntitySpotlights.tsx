/**
 * EntitySpotlights — four entity spotlight cards, all backed by live search.
 *
 * All four classes (University, Department, Course, Book) search live against
 * GET /entities/search (backend/app/api/entities.py). University and
 * Department are matched word by word (the ΟΝΤΟΛΟΓΙΑ word rules, ADR-030);
 * Course and Book by the ranking that question grounding also uses.
 *
 * ONE SEARCH, TWO VIEWS (ADR-030). A University/Department card shows the first
 * INLINE_LIMIT results of its query and, when there are more, «δείτε και τα N
 * αποτελέσματα»: that opens the modal with the SAME query, showing the whole SAME
 * server result list in one scrollable list — so the card and the modal can never
 * disagree (they used to: the modal filtered a downloaded list in the browser, a
 * second search mechanism; «λαρισα» gave 1 result in the card and 4 in the
 * modal). With an empty box the modal is the alphabetical browse list
 * (GET /entities/list, useEntityList), also scrollable. Course/Book cards have
 * no modal (73k/37k titles are not "browsable") and show up to
 * ENTITY_SEARCH_LIMIT results inline, as before.
 *
 * Nothing is searched below MIN_QUERY_LETTERS letters (user decision) — the card
 * says so instead.
 *
 * EXACT FORM (C2). Every row carries a ⧉ copy of the exact KG literal and, where
 * it differs from the readable text, an «ακριβής μορφή» disclosure — see
 * ExactForm.tsx.
 */

import { useState } from 'react'
import {
  courseSearchStats,
  bookSearchStats,
  universitySearchStats,
  departmentSearchStats,
  classes,
} from '../data/ontology'
import {
  useCourseSearch,
  useBookSearch,
  useUniversitySearch,
  useDepartmentSearch,
  queryLetters,
  ENTITY_SEARCH_LIMIT,
  INLINE_LIMIT,
  MIN_QUERY_LETTERS,
  type EntitySearchResult,
  type UseSearch,
} from '../hooks/useEntitySearch'
import { useEntityList, type ListableEntityClass } from '../hooks/useEntityList'
import { EntityModal } from './EntityModal'
import { CopyButton, ExactForm, ResultLine, primaryLiteral } from './ExactForm'
import { t } from '../i18n/el'

/** The modal shows ALL results of its query in one scrollable list (user decision) —
 * the API's maximum; the broadest 2-letter department query returns 120 (S35 M5). */
const MODAL_LIMIT = 1000

type RenderItem = (r: EntitySearchResult) => React.ReactNode

const defaultRender: RenderItem = r => <ResultLine r={r} />

/** The list's empty-state line for a query (none / too short / no results). */
function emptyLine(query: string): string {
  const letters = queryLetters(query)
  if (letters === 0) return t.ontologySearchPrompt
  if (letters < MIN_QUERY_LETTERS) return t.ontologyMinLetters
  return t.ontologyNoResults
}

// ── Shared live-search card ─────────────────────────────────────────────────

interface BrowseConfig {
  entityClass: ListableEntityClass
  /** Total shown on the "δείτε τα όλα (N)" button — known synchronously
   * (from data/ontology.ts's *SearchStats), no need to wait for the fetch. */
  total: number
  /** How to render one row inside the modal. Defaults to the card's renderer. */
  renderModalItem?: RenderItem
}

interface LiveSearchCardProps {
  titleText: string
  subLine: string
  placeholder: string
  useSearch: UseSearch
  /** How to render one row inline. Defaults to ResultLine (title + ⧉ + exact form). */
  renderItem?: RenderItem
  browse?: BrowseConfig
}

function LiveSearchCard({
  titleText,
  subLine,
  placeholder,
  useSearch,
  renderItem = defaultRender,
  browse,
}: LiveSearchCardProps) {
  const [query, setQuery] = useState('')
  // Cards with a modal show their first INLINE_LIMIT results; the others keep their longer list.
  const limit = browse ? INLINE_LIMIT : ENTITY_SEARCH_LIMIT
  const { results, total, loading, offline } = useSearch(query, { limit, offset: 0 })
  // null = closed; otherwise the query the modal opens with ('' = browse everything).
  const [modalQuery, setModalQuery] = useState<string | null>(null)
  const hasMore = queryLetters(query) >= MIN_QUERY_LETTERS && total > results.length

  return (
    <div className="od-spotlight-card">
      <h3 className="od-spotlight-title">{titleText}</h3>
      <p className="od-spotlight-sub">{subLine}</p>
      {offline && <p className="od-spotlight-offline-note">{t.ontologyOffline}</p>}

      <div className="od-search">
        <span className="od-search-icon" aria-hidden="true">⌕</span>
        <input
          className="od-search-input"
          type="search"
          placeholder={placeholder}
          value={query}
          onChange={e => setQuery(e.target.value)}
          aria-label={`${placeholder} ${titleText}`}
        />
      </div>

      <ul className="od-list" aria-label={`Λίστα ${titleText}`}>
        {loading && <li className="od-list-empty">{t.ontologySearching}</li>}
        {!loading && results.map(r => (
          <li key={r.title} className="od-list-item">{renderItem(r)}</li>
        ))}
        {!loading && results.length === 0 && <li className="od-list-empty">{emptyLine(query)}</li>}
      </ul>

      {browse && (
        <>
          <button
            className="od-show-more"
            type="button"
            onClick={() => setModalQuery(hasMore ? query : '')}
          >
            {hasMore ? t.ontologySeeAllResults(total) : t.ontologySeeAll(browse.total)}
          </button>
          {modalQuery !== null && (
            <SearchModal
              title={titleText}
              entityClass={browse.entityClass}
              useSearch={useSearch}
              initialQuery={modalQuery}
              onClose={() => setModalQuery(null)}
              renderItem={browse.renderModalItem ?? renderItem}
            />
          )}
        </>
      )}
    </div>
  )
}

// ── Modal — the SAME search, every result, one scrollable list; empty box = browse ──

function SearchModal({
  title,
  entityClass,
  useSearch,
  initialQuery,
  onClose,
  renderItem,
}: {
  title: string
  entityClass: ListableEntityClass
  useSearch: UseSearch
  initialQuery: string
  onClose: () => void
  renderItem: RenderItem
}) {
  const [query, setQuery] = useState(initialQuery)
  const searching = queryLetters(query) >= MIN_QUERY_LETTERS

  // Both hooks always run (hooks cannot be conditional); the search hook does
  // nothing below MIN_QUERY_LETTERS, the list is fetched once per open.
  const search = useSearch(query, { limit: MODAL_LIMIT, offset: 0 })
  const list = useEntityList(entityClass)

  const total = searching ? search.total : list.results.length
  const rows = searching ? search.results : list.results
  const loading = searching ? search.loading : list.loading
  const offline = searching ? search.offline : list.offline

  return (
    <EntityModal title={title} count={total} onClose={onClose}>
      {offline && <p className="od-spotlight-offline-note">{t.ontologyOffline}</p>}
      <div className="od-search">
        <span className="od-search-icon" aria-hidden="true">⌕</span>
        <input
          className="od-search-input"
          type="search"
          value={query}
          onChange={e => setQuery(e.target.value)}
          aria-label={`αναζήτηση ${title}`}
        />
      </div>
      {!searching && queryLetters(query) > 0 && <p className="od-list-empty">{t.ontologyMinLetters}</p>}
      <ul className="od-list" aria-label={`Λίστα ${title}`}>
        {loading && <li className="od-list-empty">{t.ontologySearching}</li>}
        {!loading && rows.map(r => (
          <li key={r.title} className="od-list-item">{renderItem(r)}</li>
        ))}
        {!loading && rows.length === 0 && <li className="od-list-empty">{t.ontologyNoResults}</li>}
      </ul>
    </EntityModal>
  )
}

// ── Department row rendering — badge inline, full parent names in the modal ─
//
// A department result can group several EXACT names that differ only by a
// trailing "(…)" — ΝΟΣΗΛΕΥΤΙΚΗΣ (7 universities), ΝΟΣΗΛΕΥΤΙΚΗΣ
// (ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ) (ΔΠΘ), … — because search groups on the name without the
// tail. Showing one name with every university implied that ΔΠΘ's department
// is called "ΝΟΣΗΛΕΥΤΙΚΗΣ", and hid names such as "… (ΛΑΡΙΣΑ)" entirely. So
// with several variants the row shows the shared name as a header and each
// exact name below it with ITS universities (ADR-029); with one, the row
// looks exactly as before. Every exact name has its own ⧉ and, where its KG
// literal differs from the readable text, its own exact-form disclosure (C2).

/** True when the result groups more than one exact department name. */
function hasVariants(r: EntitySearchResult): boolean {
  return (r.variants?.length ?? 0) > 1
}

function DeptInlineItem(r: EntitySearchResult) {
  const parents = r.parents ?? []
  if (hasVariants(r)) {
    return (
      <span className="od-list-item-detail">
        <span className="od-list-item--dept">
          <span className="od-list-item-name">{r.title}</span>
          <span className="od-list-item-badge">{t.ontologyDeptVariantsNote(r.variants!.length)}</span>
        </span>
        <ul className="od-dept-variants">
          {r.variants!.map(v => (
            <li key={v.name} className="od-list-item-detail">
              <span className="od-list-item--dept">
                <span className="od-list-item-name">{v.name}</span>
                <CopyButton text={v.literal ?? v.name} />
                <span className="od-list-item-badge">{t.ontologyDeptSharedNote(v.parents.length)}</span>
              </span>
              <ExactForm display={v.name} literals={v.literal ? [v.literal] : []} />
            </li>
          ))}
        </ul>
      </span>
    )
  }
  return (
    <span className="od-list-item-detail">
      <span className="od-list-item--dept">
        <span className="od-list-item-name">{r.title}</span>
        <CopyButton text={primaryLiteral(r)} />
        {parents.length > 1 && (
          <span className="od-list-item-badge">{t.ontologyDeptSharedNote(parents.length)}</span>
        )}
      </span>
      <ExactForm display={r.title} literals={r.literals ?? []} />
    </span>
  )
}

function DeptModalItem(r: EntitySearchResult) {
  const parents = r.parents ?? []
  if (hasVariants(r)) {
    return (
      <span className="od-list-item-detail">
        <span className="od-list-item-name">{r.title}</span>
        <ul className="od-dept-variants">
          {r.variants!.map(v => (
            <li key={v.name} className="od-list-item-detail">
              <span className="od-result-line">
                <span className="od-list-item-name">{v.name}</span>
                <CopyButton text={v.literal ?? v.name} />
              </span>
              <span className="od-list-item-parents">
                {t.ontologyDeptParentsLabel}: {v.parents.join(', ')}
              </span>
              <ExactForm display={v.name} literals={v.literal ? [v.literal] : []} />
            </li>
          ))}
        </ul>
      </span>
    )
  }
  return (
    <span className="od-list-item-detail">
      <span className="od-result-line">
        <span className="od-list-item-name">{r.title}</span>
        <CopyButton text={primaryLiteral(r)} />
      </span>
      {parents.length > 0 && (
        <span className="od-list-item-parents">
          {t.ontologyDeptParentsLabel}: {parents.join(', ')}
        </span>
      )}
      <ExactForm display={r.title} literals={r.literals ?? []} />
    </span>
  )
}

// ── Main export ───────────────────────────────────────────────────────────────

export function EntitySpotlights() {
  const universityTotal = classes.find(c => c.id === 'University')?.count ?? universitySearchStats.distinctNames
  const departmentTotal = classes.find(c => c.id === 'Department')?.count ?? departmentSearchStats.distinctNames

  return (
    <div className="od-spotlights">
      <LiveSearchCard
        titleText={t.ontologySpotUniTitle}
        subLine={t.ontologySpotUniSub(universitySearchStats.distinctNames, universityTotal)}
        placeholder={t.ontologyUniSearchPlaceholder}
        useSearch={useUniversitySearch}
        browse={{ entityClass: 'university', total: universitySearchStats.distinctNames }}
      />
      <LiveSearchCard
        titleText={t.ontologySpotDeptTitle}
        subLine={t.ontologySpotDeptSub(departmentTotal, departmentSearchStats.distinctNames)}
        placeholder={t.ontologyDeptSearchPlaceholder}
        useSearch={useDepartmentSearch}
        renderItem={DeptInlineItem}
        browse={{
          entityClass: 'department',
          total: departmentSearchStats.distinctNames,
          renderModalItem: DeptModalItem,
        }}
      />
      <LiveSearchCard
        titleText={t.ontologySpotCourseTitle}
        subLine={t.ontologySpotCourseSub(
          courseSearchStats.distinctTitlesFormatted,
          classes.find(c => c.id === 'Course')?.countFormatted ?? '',
        )}
        placeholder={t.ontologyCourseSearchPlaceholder}
        useSearch={useCourseSearch}
      />
      <LiveSearchCard
        titleText={t.ontologySpotBookTitle}
        subLine={t.ontologySpotBookSub(
          bookSearchStats.distinctTitlesFormatted,
          classes.find(c => c.id === 'Book')?.countFormatted ?? '',
        )}
        placeholder={t.ontologyBookSearchPlaceholder}
        useSearch={useBookSearch}
      />
    </div>
  )
}
