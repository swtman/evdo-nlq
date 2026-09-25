/**
 * useEntitySearch — debounced entity search against GET /entities/search.
 *
 * One backend search serves both views of a ΟΝΤΟΛΟΓΙΑ card (ADR-030): the card
 * asks for its first INLINE_LIMIT results, the «δείτε και τα N αποτελέσματα»
 * modal for all results of the SAME query (one scrollable list) — so the two can
 * never disagree, and `total` is the number of all matches. University and
 * department are matched by the backend's word rules (title_index/word_search.py);
 * course and book by `rank_titles` (see backend/app/api/entities.py, "LOOKUP IS
 * NOT LINKING"). Shared by the four `use*Search` wrappers below rather than
 * duplicated, because the debounce, the stale-response race guard, and the
 * offline fallback are three subtle behaviors that would otherwise drift apart.
 *
 * Nothing is searched below MIN_QUERY_LETTERS letters — the card shows its
 * prompt instead (user decision, 2026-09-25; the backend enforces the same).
 *
 * Falls back to a small offline sample when:
 *   - VITE_USE_MOCK_API=1 (frontend UI dev without a backend), or
 *   - the fetch fails (backend not running / network error).
 * Both cases are surfaced via `offline: true` so the UI can label the
 * fallback honestly rather than presenting it as a live search result.
 */

import { useEffect, useRef, useState } from 'react'
import {
  SAMPLE_COURSE_TITLES,
  SAMPLE_BOOK_TITLES,
  SAMPLE_UNIVERSITY_TITLES,
  SAMPLE_DEPARTMENT_TITLES,
} from '../data/ontology'

const DEBOUNCE_MS = 250

/** How many results the course/book cards show (they have no modal); the default request size. */
export const ENTITY_SEARCH_LIMIT = 50

/** Results a university/department card shows before «δείτε και τα N» (user decision). */
export const INLINE_LIMIT = 8

/** Letters needed before anything is searched — same rule as the backend. */
export const MIN_QUERY_LETTERS = 2

export type EntityClass = 'course' | 'book' | 'university' | 'department'

/** One exact department name inside a result, with the universities that have it. */
export interface DepartmentVariant {
  /** Display form of the exact KG name, e.g. "ΝΟΣΗΛΕΥΤΙΚΗΣ (ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ)". */
  name: string
  parents: string[]
  /** The same name exactly as stored in the KG, whitespace untouched (C2 copy). */
  literal?: string
}

export interface EntitySearchResult {
  title: string
  score: number
  /** Parent university name(s) — populated only for class='department'. */
  parents?: string[]
  /**
   * class='department' only: every exact name grouped into this result, each
   * with its own universities. A result groups names that differ only by a
   * trailing "(…)" (ΝΟΣΗΛΕΥΤΙΚΗΣ, ΝΟΣΗΛΕΥΤΙΚΗΣ (ΑΛΕΞΑΝΔΡΟΥΠΟΛΗ), …); with
   * several, `title` is the shared name and these list the real ones
   * (ADR-029). Absent in the offline sample.
   */
  variants?: DepartmentVariant[]
  /**
   * Every KG literal of this result exactly as stored — `title` is a tidied display
   * form; these are what a hand-written SPARQL query must use (ADR-030 C2).
   * Absent in the offline sample.
   */
  literals?: string[]
}

/** Which slice of the ranked results to fetch. */
export interface SearchPage {
  limit: number
  offset: number
}

export interface EntitySearchState {
  results: EntitySearchResult[]
  /** Number of ALL matches of the query (not just this page). */
  total: number
  loading: boolean
  /** True when results come from the offline sample, not a live search. */
  offline: boolean
}

export type UseSearch = (query: string, page?: SearchPage) => EntitySearchState

const SAMPLE_TITLES: Record<EntityClass, string[]> = {
  course: SAMPLE_COURSE_TITLES,
  book: SAMPLE_BOOK_TITLES,
  university: SAMPLE_UNIVERSITY_TITLES,
  department: SAMPLE_DEPARTMENT_TITLES,
}

const MOCK = import.meta.env.VITE_USE_MOCK_API === '1'

/**
 * Accent-fold a Greek (or any) string for comparison: NFD-decompose so tone
 * marks become separate code points, then strip them and lowercase.
 * Mirrors the backend's `normalize_greek` (app/grounding/normalize.py) so
 * this offline fallback behaves the same way the real search does — an
 * unaccented query like "δικτυα" must still match "Δίκτυα Υπολογιστών".
 */
export function foldGreek(s: string): string {
  // \p{M} = Unicode general category "Mark" — every combining diacritic
  // (Greek tone marks included) in one property escape, no raw glyphs
  // needed in source. Requires the /u flag.
  return s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()
}

/** Letters and digits in a query — what counts toward MIN_QUERY_LETTERS. */
export function queryLetters(query: string): number {
  return foldGreek(query).replace(/[^\p{L}\p{N}]/gu, '').length
}

/** Offline fallback: substring over the sample titles (labelled offline in the UI). */
function searchSampleTitles(entityClass: EntityClass, query: string): EntitySearchResult[] {
  const q = foldGreek(query.trim())
  return SAMPLE_TITLES[entityClass]
    .filter(title => foldGreek(title).includes(q))
    .map(title => ({ title, score: 1 }))
}

function samplePage(entityClass: EntityClass, query: string, page: SearchPage): EntitySearchState {
  const all = searchSampleTitles(entityClass, query)
  return {
    results: all.slice(page.offset, page.offset + page.limit),
    total: all.length,
    loading: false,
    offline: true,
  }
}

export function useEntitySearch(
  query: string,
  entityClass: EntityClass,
  page: SearchPage = { limit: ENTITY_SEARCH_LIMIT, offset: 0 },
): EntitySearchState {
  const [state, setState] = useState<EntitySearchState>({
    results: [],
    total: 0,
    loading: false,
    offline: MOCK,
  })

  // Tracks the most recently issued request so a slow earlier response
  // can't overwrite a faster later one (classic debounce race).
  const requestId = useRef(0)
  const { limit, offset } = page

  useEffect(() => {
    const thisRequest = ++requestId.current

    if (queryLetters(query) < MIN_QUERY_LETTERS) {
      setState({ results: [], total: 0, loading: false, offline: MOCK })
      return
    }
    if (MOCK) {
      setState(samplePage(entityClass, query, { limit, offset }))
      return
    }

    setState(prev => ({ ...prev, loading: true }))
    const handle = setTimeout(() => {
      const params = new URLSearchParams({
        q: query,
        class: entityClass,
        limit: String(limit),
        offset: String(offset),
      })
      fetch(`/entities/search?${params}`)
        .then(res => {
          if (!res.ok) throw new Error(`search failed: ${res.status}`)
          return res.json() as Promise<{ results: EntitySearchResult[]; total: number }>
        })
        .then(data => {
          if (requestId.current !== thisRequest) return // stale response, ignore
          setState({ results: data.results, total: data.total, loading: false, offline: false })
        })
        .catch(() => {
          if (requestId.current !== thisRequest) return
          setState(samplePage(entityClass, query, { limit, offset }))
        })
    }, DEBOUNCE_MS)

    return () => clearTimeout(handle)
  }, [query, entityClass, limit, offset])

  return state
}

export const useCourseSearch: UseSearch = (query, page) => useEntitySearch(query, 'course', page)
export const useBookSearch: UseSearch = (query, page) => useEntitySearch(query, 'book', page)
export const useUniversitySearch: UseSearch = (query, page) =>
  useEntitySearch(query, 'university', page)
export const useDepartmentSearch: UseSearch = (query, page) =>
  useEntitySearch(query, 'department', page)
