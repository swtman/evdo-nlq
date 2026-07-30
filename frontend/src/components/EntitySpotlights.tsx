/**
 * EntitySpotlights — side-by-side entity spotlight cards.
 *
 * Cards:
 *   1. Universities — compact preview + "δείτε τα όλα" opens a searchable modal.
 *      Data: bundled entities.json (46 records — small enough to ship in the bundle).
 *   2. Departments  — same pattern; de-duped names annotated with sharing-uni count.
 *      Data: bundled entities.json (799 records).
 *   3. Courses      — live debounced search against GET /entities/search, the
 *      same endpoint the SPARQL grounding pipeline resolves course mentions
 *      through (see backend/app/api/entities.py). Not bundled: ~73k distinct
 *      titles would be an 8 MB import for a feature that only needs the top
 *      few ranked matches per keystroke — see ADR-018.
 *
 * The Books card was removed (2026-07-30): it depended on a `sampleBooks`
 * export that no longer exists in ontology.ts, and no book title corpus has
 * been built yet (course titles only — see ADR-018 "Deferred"). It returns
 * once a book corpus exists, following the same live-search pattern as
 * CourseCard.
 */

import { useState, useMemo } from 'react'
import entitiesRaw from '../data/entities.json'
import { courseSearchStats, classes } from '../data/ontology'
import { useCourseSearch } from '../hooks/useCourseSearch'
import { EntityModal } from './EntityModal'
import { t } from '../i18n/el'

/** Shape of entities.json */
interface EntitiesData {
  snapshot: string
  universities: string[]
  departments: { university: string; department: string }[]
}

const entities = entitiesRaw as EntitiesData

/** Max items shown inline before the "see all" modal button */
const LIST_MAX = 8

// ── University card ───────────────────────────────────────────────────────────

function UniversityCard() {
  const [query, setQuery]       = useState('')
  const [modalOpen, setModalOpen] = useState(false)

  const totalInstances = classes.find(c => c.id === 'University')?.count ?? 46

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return entities.universities
    return entities.universities.filter(u => u.toLowerCase().includes(q))
  }, [query])

  return (
    <div className="od-spotlight-card">
      <h3 className="od-spotlight-title">{t.ontologySpotUniTitle}</h3>
      <p className="od-spotlight-sub">
        {t.ontologySpotUniSub(entities.universities.length, totalInstances)}
      </p>

      <div className="od-search">
        <span className="od-search-icon" aria-hidden="true">⌕</span>
        <input
          className="od-search-input"
          type="search"
          placeholder={t.ontologySearchPlaceholder}
          value={query}
          onChange={e => setQuery(e.target.value)}
          aria-label={`${t.ontologySearchPlaceholder} ${t.ontologySpotUniTitle}`}
        />
      </div>

      <ul className="od-list" aria-label={`Λίστα ${t.ontologySpotUniTitle}`}>
        {filtered.slice(0, LIST_MAX).map(u => (
          <li key={u} className="od-list-item">{u}</li>
        ))}
        {filtered.length === 0 && <li className="od-list-empty">—</li>}
      </ul>

      <button
        className="od-show-more"
        type="button"
        onClick={() => setModalOpen(true)}
      >
        {t.ontologySeeAll(entities.universities.length)}
      </button>

      {modalOpen && (
        <EntityModal
          title={t.ontologySpotUniTitle}
          count={filtered.length}
          onClose={() => setModalOpen(false)}
        >
          <div className="od-search">
            <span className="od-search-icon" aria-hidden="true">⌕</span>
            <input
              className="od-search-input"
              type="search"
              placeholder={t.ontologySearchPlaceholder}
              value={query}
              onChange={e => setQuery(e.target.value)}
              aria-label={`${t.ontologySearchPlaceholder} ${t.ontologySpotUniTitle}`}
            />
          </div>
          <ul className="od-list" aria-label={`Λίστα ${t.ontologySpotUniTitle}`}>
            {filtered.map(u => (
              <li key={u} className="od-list-item">{u}</li>
            ))}
            {filtered.length === 0 && <li className="od-list-empty">—</li>}
          </ul>
        </EntityModal>
      )}
    </div>
  )
}

// ── Department card ───────────────────────────────────────────────────────────

/** Grouped dept info: how many universities share this department name */
interface DeptGroup {
  name: string
  uniCount: number
}

function buildDeptGroups(): DeptGroup[] {
  const map = new Map<string, Set<string>>()
  for (const { university, department } of entities.departments) {
    if (!map.has(department)) map.set(department, new Set())
    map.get(department)!.add(university)
  }
  return Array.from(map.entries())
    .map(([name, unis]) => ({ name, uniCount: unis.size }))
    .sort((a, b) => a.name.localeCompare(b.name, 'el'))
}

const deptGroups = buildDeptGroups()

function DepartmentCard() {
  const [query, setQuery]       = useState('')
  const [modalOpen, setModalOpen] = useState(false)

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return deptGroups
    return deptGroups.filter(d => d.name.toLowerCase().includes(q))
  }, [query])

  function DeptList({ items }: { items: DeptGroup[] }) {
    return (
      <ul className="od-list" aria-label={`Λίστα ${t.ontologySpotDeptTitle}`}>
        {items.map(d => (
          <li key={d.name} className="od-list-item od-list-item--dept">
            <span className="od-list-item-name">{d.name}</span>
            {d.uniCount > 1 && (
              <span className="od-list-item-badge">
                {t.ontologyDeptSharedNote(d.uniCount)}
              </span>
            )}
          </li>
        ))}
        {items.length === 0 && <li className="od-list-empty">—</li>}
      </ul>
    )
  }

  return (
    <div className="od-spotlight-card">
      <h3 className="od-spotlight-title">{t.ontologySpotDeptTitle}</h3>
      <p className="od-spotlight-sub">
        {t.ontologySpotDeptSub(deptGroups.length)}
      </p>

      <div className="od-search">
        <span className="od-search-icon" aria-hidden="true">⌕</span>
        <input
          className="od-search-input"
          type="search"
          placeholder={t.ontologySearchPlaceholder}
          value={query}
          onChange={e => setQuery(e.target.value)}
          aria-label={`${t.ontologySearchPlaceholder} ${t.ontologySpotDeptTitle}`}
        />
      </div>

      <DeptList items={filtered.slice(0, LIST_MAX)} />

      <button
        className="od-show-more"
        type="button"
        onClick={() => setModalOpen(true)}
      >
        {t.ontologySeeAll(deptGroups.length)}
      </button>

      {modalOpen && (
        <EntityModal
          title={t.ontologySpotDeptTitle}
          count={filtered.length}
          onClose={() => setModalOpen(false)}
        >
          <div className="od-search">
            <span className="od-search-icon" aria-hidden="true">⌕</span>
            <input
              className="od-search-input"
              type="search"
              placeholder={t.ontologySearchPlaceholder}
              value={query}
              onChange={e => setQuery(e.target.value)}
              aria-label={`${t.ontologySearchPlaceholder} ${t.ontologySpotDeptTitle}`}
            />
          </div>
          <DeptList items={filtered} />
        </EntityModal>
      )}
    </div>
  )
}

// ── Course card ─────────────────────────────────────────────────────────────
//
// Unlike University/Department (bundled list, client-side filter), course
// search is live: each keystroke (debounced) queries GET /entities/search,
// which ranks the ~73k-title corpus server-side and returns only the top
// matches. There is no separate "preview 8 / see all N" tier here — the
// results ARE already the top-ranked matches, so a "see all" modal would
// misleadingly imply a larger exhaustive list exists behind it. Instead the
// full result list (up to the endpoint's limit) renders inline, with a
// loading state during the debounce window and an explicit offline label
// when falling back to the local sample (see useCourseSearch).

const COURSE_RESULTS_SHOWN = 100

function CourseCard() {
  const [query, setQuery] = useState('')
  const { results, loading, offline } = useCourseSearch(query)
  const shown = results.slice(0, COURSE_RESULTS_SHOWN)

  return (
    <div className="od-spotlight-card">
      <h3 className="od-spotlight-title">{t.ontologySpotCourseTitle}</h3>
      <p className="od-spotlight-sub">
        {t.ontologySpotCourseSub(
          courseSearchStats.distinctTitlesFormatted,
          classes.find(c => c.id === 'Course')?.countFormatted ?? '',
        )}
      </p>
      {offline && <p className="od-spotlight-offline-note">{t.ontologyCourseOffline}</p>}

      <div className="od-search">
        <span className="od-search-icon" aria-hidden="true">⌕</span>
        <input
          className="od-search-input"
          type="search"
          placeholder={t.ontologyCourseSearchPlaceholder}
          value={query}
          onChange={e => setQuery(e.target.value)}
          aria-label={`${t.ontologyCourseSearchPlaceholder} ${t.ontologySpotCourseTitle}`}
        />
      </div>

      <ul className="od-list" aria-label={`Λίστα ${t.ontologySpotCourseTitle}`}>
        {loading && <li className="od-list-empty">{t.ontologySearching}</li>}
        {!loading && shown.map(r => (
          <li key={r.title} className="od-list-item">{r.title}</li>
        ))}
        {!loading && shown.length === 0 && (
          <li className="od-list-empty">{t.ontologyCourseNoResults}</li>
        )}
      </ul>
    </div>
  )
}

// ── Main export ───────────────────────────────────────────────────────────────

export function EntitySpotlights() {
  return (
    <div className="od-spotlights">
      <UniversityCard />
      <DepartmentCard />
      <CourseCard />
    </div>
  )
}
