/**
 * useEntitySearch — debounced entity search against GET /entities/search.
 *
 * Calls the SAME backend function the SPARQL grounding pipeline uses to
 * resolve an entity named inside a question (see backend/app/api/entities.py)
 * — so an entity found here is exactly one the pipeline is capable of
 * matching from natural language (course/book via hints.py's title
 * resolution; university/department via linker.py's Stage 3, which shares
 * the same score threshold — see ADR-020). Shared by the four `use*Search`
 * wrappers below rather than duplicated, because the debounce, the
 * stale-response race guard, and the offline fallback are three subtle
 * behaviors that would otherwise drift between four copies.
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

// Single source of truth for the search result cap, shared by the fetch
// call below and by EntitySpotlights' display slice — previously two
// separate constants (limit: '50' here, RESULTS_SHOWN = 100 there) where
// the second one was a silent no-op because the API already caps at 50.
export const ENTITY_SEARCH_LIMIT = 50

export type EntityClass = 'course' | 'book' | 'university' | 'department'

export interface EntitySearchResult {
  title: string
  score: number
  /** Parent university name(s) — populated only for class='department'. */
  parents?: string[]
}

interface EntitySearchState {
  results: EntitySearchResult[]
  loading: boolean
  /** True when results come from the offline sample, not a live search. */
  offline: boolean
}

const SAMPLE_TITLES: Record<EntityClass, string[]> = {
  course: SAMPLE_COURSE_TITLES,
  book: SAMPLE_BOOK_TITLES,
  university: SAMPLE_UNIVERSITY_TITLES,
  department: SAMPLE_DEPARTMENT_TITLES,
}

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

function searchSampleTitles(entityClass: EntityClass, query: string): EntitySearchResult[] {
  const titles = SAMPLE_TITLES[entityClass]
  const q = foldGreek(query.trim())
  if (!q) return titles.map(title => ({ title, score: 1 }))
  return titles
    .filter(title => foldGreek(title).includes(q))
    .map(title => ({ title, score: 1 }))
}

function useEntitySearch(query: string, entityClass: EntityClass): EntitySearchState {
  const [state, setState] = useState<EntitySearchState>({
    results: searchSampleTitles(entityClass, ''),
    loading: false,
    offline: import.meta.env.VITE_USE_MOCK_API === '1',
  })

  // Tracks the most recently issued request so a slow earlier response
  // can't overwrite a faster later one (classic debounce race).
  const requestId = useRef(0)

  useEffect(() => {
    if (import.meta.env.VITE_USE_MOCK_API === '1') {
      setState({ results: searchSampleTitles(entityClass, query), loading: false, offline: true })
      return
    }

    const thisRequest = ++requestId.current
    setState(prev => ({ ...prev, loading: true }))

    const handle = setTimeout(() => {
      const params = new URLSearchParams({
        q: query || ' ',
        class: entityClass,
        limit: String(ENTITY_SEARCH_LIMIT),
      })
      fetch(`/entities/search?${params}`)
        .then(res => {
          if (!res.ok) throw new Error(`search failed: ${res.status}`)
          return res.json() as Promise<{ results: EntitySearchResult[] }>
        })
        .then(data => {
          if (requestId.current !== thisRequest) return // stale response, ignore
          setState({ results: data.results, loading: false, offline: false })
        })
        .catch(() => {
          if (requestId.current !== thisRequest) return
          setState({ results: searchSampleTitles(entityClass, query), loading: false, offline: true })
        })
    }, DEBOUNCE_MS)

    return () => clearTimeout(handle)
  }, [query, entityClass])

  return state
}

export function useCourseSearch(query: string): EntitySearchState {
  return useEntitySearch(query, 'course')
}

export function useBookSearch(query: string): EntitySearchState {
  return useEntitySearch(query, 'book')
}

export function useUniversitySearch(query: string): EntitySearchState {
  return useEntitySearch(query, 'university')
}

export function useDepartmentSearch(query: string): EntitySearchState {
  return useEntitySearch(query, 'department')
}
