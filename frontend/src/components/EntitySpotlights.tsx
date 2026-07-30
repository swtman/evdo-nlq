/**
 * EntitySpotlights — three side-by-side entity spotlight cards.
 *
 * Cards:
 *   1. Universities — compact preview + "δείτε τα όλα" opens a searchable modal
 *   2. Departments  — same pattern; de-duped names annotated with sharing-uni count
 *   3. Books        — shows one selected book record; "δείτε τα όλα" modal picks another
 *   4. Courses      — shows one selected course record; "δείτε τα όλα" modal picks another
 *
 * All data is local (entities.json, ontology.ts); no network calls (display-only).
 */

import { useState, useMemo } from 'react'
import entitiesRaw from '../data/entities.json'
import { classes } from '../data/ontology'
import { EntityModal } from './EntityModal'
import { t } from '../i18n/el'

/** Shape of entities.json */
interface EntitiesData {
  snapshot: string
  universities: string[]
  departments: { university: string; department: string }[]
  courses: string[]
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

function CourseCard() {
  const [selectedIdx, setSelectedIdx] = useState(0)
  const [modalOpen,   setModalOpen]   = useState(false)
  const [courseQuery, setCourseQuery]  = useState('')

  const course = entities.courses[selectedIdx]

  const filteredCourses = useMemo(() => {
    const q = courseQuery.trim().toLowerCase()
    if (!q) return entities.courses
    return entities.courses.filter(c => c.toLowerCase().includes(q))
  }, [courseQuery])

  return (
    <div className="od-spotlight-card">
      <h3 className="od-spotlight-title">{t.ontologySpotCourseTitle}</h3>
      <p className="od-spotlight-sub">{t.ontologySpotCourseSub(entities.courses.length, classes.find(c => c.id === 'Course')?.count ?? 0
      )}</p>

      <div className="od-book-title">{course}</div>

      <button
        className="od-show-more"
        type="button"
        onClick={() => setModalOpen(true)}
      >
        {t.ontologySeeAll(entities.courses.length)}
      </button>

      {modalOpen && (
        <EntityModal
          title={t.ontologySpotCourseTitle}
          count={filteredCourses.length}
          onClose={() => setModalOpen(false)}
        >
          <div className="od-search">
            <span className="od-search-icon" aria-hidden="true">⌕</span>
            <input
              className="od-search-input"
              type="search"
              placeholder={t.ontologySearchPlaceholder}
              value={courseQuery}
              onChange={e => setCourseQuery(e.target.value)}
              aria-label={`${t.ontologySearchPlaceholder} ${t.ontologySpotCourseTitle}`}
            />
          </div>
          <ul className="od-list" aria-label={`Λίστα ${t.ontologySpotCourseTitle}`}>
            {filteredCourses.map(c => {
              const realIdx = entities.courses.indexOf(c)
              return (
                <li key={c} className="od-list-item od-list-item--selectable">
                  <button
                    type="button"
                    className={`od-list-item-btn${realIdx === selectedIdx ? ' od-list-item-btn--active' : ''}`}
                    onClick={() => { setSelectedIdx(realIdx); setModalOpen(false) }}
                    aria-current={realIdx === selectedIdx ? 'true' : undefined}
                  >
                    <span className="od-list-item-name">{c}</span>
                  </button>
                </li>
              )
            })}
            {filteredCourses.length === 0 && (
              <li className="od-list-empty">—</li>
            )}
          </ul>
        </EntityModal>
      )}
    </div>
  )
}

// // ── Book sample card ──────────────────────────────────────────────────────────

function BookCard() {
  const bookCount    = classes.find(c => c.id === 'Book')?.countFormatted ?? '48.679'
  const [selectedIdx, setSelectedIdx] = useState(0)
  const [modalOpen,   setModalOpen]   = useState(false)
  const [bookQuery,   setBookQuery]   = useState('')

  const book = sampleBooks[selectedIdx]

  const filteredBooks = useMemo(() => {
    const q = bookQuery.trim().toLowerCase()
    if (!q) return sampleBooks
    return sampleBooks.filter(
      b => b.title.toLowerCase().includes(q) || b.authors.toLowerCase().includes(q)
    )
  }, [bookQuery])

  return (
    <div className="od-spotlight-card">
      <h3 className="od-spotlight-title">{t.ontologySpotBookTitle}</h3>
      <p className="od-spotlight-sub">{t.ontologySpotBookSub(bookCount)}</p>

      <dl className="od-book-record">
        <dt>{t.ontologyBookCode}</dt>
        <dd className="od-book-code">{book.code}</dd>

        <dt>{t.ontologyBookAuthors}</dt>
        <dd>{book.authors}</dd>

        <dt>{t.ontologyBookIsbn}</dt>
        <dd>{book.isbn}</dd>

        <dt>{t.ontologyBookKeywords}</dt>
        <dd className="od-book-keywords">
          {book.keywords.map(kw => (
            <span key={kw} className="od-kw-chip">{kw}</span>
          ))}
        </dd>

        <dt>{t.ontologyBookPublisher}</dt>
        <dd>{book.publisher}</dd>
      </dl>

      <div className="od-book-title">{book.title}</div>

      <button
        className="od-show-more"
        type="button"
        onClick={() => setModalOpen(true)}
      >
        {t.ontologySeeAll(sampleBooks.length)}
      </button>

      {modalOpen && (
        <EntityModal
          title={t.ontologyBookModalTitle}
          count={filteredBooks.length}
          onClose={() => setModalOpen(false)}
        >
          <div className="od-search">
            <span className="od-search-icon" aria-hidden="true">⌕</span>
            <input
              className="od-search-input"
              type="search"
              placeholder={t.ontologySearchPlaceholder}
              value={bookQuery}
              onChange={e => setBookQuery(e.target.value)}
              aria-label={`${t.ontologySearchPlaceholder} ${t.ontologyBookModalTitle}`}
            />
          </div>
          <ul className="od-list" aria-label="Λίστα βιβλίων">
            {filteredBooks.map(b => {
              const realIdx = sampleBooks.indexOf(b)
              return (
                <li key={b.code} className="od-list-item od-list-item--selectable">
                  <button
                    type="button"
                    className={`od-list-item-btn${realIdx === selectedIdx ? ' od-list-item-btn--active' : ''}`}
                    onClick={() => { setSelectedIdx(realIdx); setModalOpen(false) }}
                    aria-current={realIdx === selectedIdx ? 'true' : undefined}
                  >
                    <span className="od-list-item-name">{b.title}</span>
                    <span className="od-list-item-badge">{b.authors.split(' / ')[0]}</span>
                  </button>
                </li>
              )
            })}
            {filteredBooks.length === 0 && (
              <li className="od-list-empty">—</li>
            )}
          </ul>
        </EntityModal>
      )}
    </div>
  )
}

// ── Main export ───────────────────────────────────────────────────────────────

export function EntitySpotlights() {
  return (
    <div className="od-spotlights">
      <UniversityCard />
      <DepartmentCard />
      {/* <CourseCard /> */}
      {/* BookCard — needs sampleBooks from ontology.ts; to be restored */}
    </div>
  )
}
