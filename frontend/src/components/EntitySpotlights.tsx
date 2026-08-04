/**
 * EntitySpotlights — four entity spotlight cards, all backed by live search.
 *
 * All four classes (University, Department, Course, Book) now go through
 * the exact same pattern: a debounced live search against
 * GET /entities/search (see backend/app/api/entities.py, ADR-018/ADR-020) —
 * each keystroke ranks the real corpus server-side and returns only the top
 * matches. This used to be true only for Course/Book; University/Department
 * shipped their entire list inside the JS bundle (data/entities.json, 46 +
 * 799 records) and filtered it client-side. That bundle is gone — see
 * ADR-020 for why: it duplicated data already served live, and meant a
 * university a user could find by browsing here was not provably one
 * Stage-1 grounding could resolve from a question (the whole guarantee
 * ADR-018 established for Course/Book).
 *
 * University and Department additionally get a "δείτε τα όλα" browse
 * modal — genuinely different from search (there's no ranking to "browse
 * everything", so it can't reuse the search results) — fed by a SEPARATE
 * endpoint, GET /entities/list, and a separate hook, useEntityList. Course
 * and Book don't: at ~73k/~37k distinct titles, listing "everything" isn't
 * a coherent UI action the way it is for 46 universities.
 *
 * The four cards share one component, LiveSearchCard, parameterized by
 * which useXSearch hook to call and (for University/Department) the browse
 * config — see that component for the shared layout.
 */

import { useMemo, useState } from 'react'
import { courseSearchStats, bookSearchStats, universitySearchStats, departmentSearchStats, classes } from '../data/ontology'
import {
  useCourseSearch,
  useBookSearch,
  useUniversitySearch,
  useDepartmentSearch,
  foldGreek,
  ENTITY_SEARCH_LIMIT,
  type EntitySearchResult,
} from '../hooks/useEntitySearch'
import { useEntityList, type ListableEntityClass } from '../hooks/useEntityList'
import { EntityModal } from './EntityModal'
import { t } from '../i18n/el'

// ── Shared live-search card ─────────────────────────────────────────────────

interface BrowseConfig {
  entityClass: ListableEntityClass
  /** Total shown on the "δείτε τα όλα (N)" button — known synchronously
   * (from data/ontology.ts's *SearchStats), no need to wait for the fetch. */
  total: number
  /** How to render one row inside the browse modal. Defaults to plain title. */
  renderModalItem?: (r: EntitySearchResult) => React.ReactNode
}

interface LiveSearchCardProps {
  titleText: string
  subLine: string
  placeholder: string
  useSearch: (query: string) => { results: EntitySearchResult[]; loading: boolean; offline: boolean }
  /** How to render one row inline. Defaults to plain title. */
  renderItem?: (r: EntitySearchResult) => React.ReactNode
  browse?: BrowseConfig
}

function LiveSearchCard({
  titleText,
  subLine,
  placeholder,
  useSearch,
  renderItem = r => r.title,
  browse,
}: LiveSearchCardProps) {
  const [query, setQuery] = useState('')
  const { results, loading, offline } = useSearch(query)
  const shown = results.slice(0, ENTITY_SEARCH_LIMIT)
  const [modalOpen, setModalOpen] = useState(false)

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
        {!loading && shown.map(r => (
          <li key={r.title} className="od-list-item">{renderItem(r)}</li>
        ))}
        {!loading && shown.length === 0 && query.trim() === '' && (
          <li className="od-list-empty">{t.ontologySearchPrompt}</li>
        )}
        {!loading && shown.length === 0 && query.trim() !== '' && (
          <li className="od-list-empty">{t.ontologyNoResults}</li>
        )}
      </ul>

      {browse && (
        <>
          <button className="od-show-more" type="button" onClick={() => setModalOpen(true)}>
            {t.ontologySeeAll(browse.total)}
          </button>
          {modalOpen && (
            <BrowseModal
              title={titleText}
              entityClass={browse.entityClass}
              onClose={() => setModalOpen(false)}
              renderItem={browse.renderModalItem ?? (r => r.title)}
            />
          )}
        </>
      )}
    </div>
  )
}

// ── Browse modal — "δείτε τα όλα", backed by GET /entities/list ───────────

function BrowseModal({
  title,
  entityClass,
  onClose,
  renderItem,
}: {
  title: string
  entityClass: ListableEntityClass
  onClose: () => void
  renderItem: (r: EntitySearchResult) => React.ReactNode
}) {
  const { results, loading, offline } = useEntityList(entityClass)
  const [query, setQuery] = useState('')

  const filtered = useMemo(() => {
    const q = foldGreek(query.trim())
    if (!q) return results
    return results.filter(r => foldGreek(r.title).includes(q))
  }, [results, query])

  return (
    <EntityModal title={title} count={filtered.length} onClose={onClose}>
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
      <ul className="od-list" aria-label={`Λίστα ${title}`}>
        {loading && <li className="od-list-empty">{t.ontologySearching}</li>}
        {!loading && filtered.map(r => (
          <li key={r.title} className="od-list-item">{renderItem(r)}</li>
        ))}
        {!loading && filtered.length === 0 && (
          <li className="od-list-empty">{t.ontologyNoResults}</li>
        )}
      </ul>
    </EntityModal>
  )
}

// ── Department row rendering — badge inline, full parent names in the modal ─

function DeptInlineItem(r: EntitySearchResult) {
  const parents = r.parents ?? []
  return (
    <span className="od-list-item--dept">
      <span className="od-list-item-name">{r.title}</span>
      {parents.length > 1 && (
        <span className="od-list-item-badge">{t.ontologyDeptSharedNote(parents.length)}</span>
      )}
    </span>
  )
}

function DeptModalItem(r: EntitySearchResult) {
  const parents = r.parents ?? []
  return (
    <span className="od-list-item-detail">
      <span className="od-list-item-name">{r.title}</span>
      {parents.length > 0 && (
        <span className="od-list-item-parents">
          {t.ontologyDeptParentsLabel}: {parents.join(', ')}
        </span>
      )}
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
