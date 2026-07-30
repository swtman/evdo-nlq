/**
 * useCourseSearch — debounced course-title search against GET /entities/search.
 *
 * Calls the SAME backend function the SPARQL grounding pipeline uses to
 * resolve a course named inside a question (see backend/app/api/entities.py)
 * — so a course found here is exactly a course the pipeline is capable of
 * matching from natural language.
 *
 * Falls back to a small offline sample (SAMPLE_COURSE_TITLES) when:
 *   - VITE_USE_MOCK_API=1 (frontend UI dev without a backend), or
 *   - the fetch fails (backend not running / network error).
 * Both cases are surfaced via `offline: true` so the UI can label the
 * fallback honestly rather than presenting it as a live search result.
 */

import { useEffect, useRef, useState } from 'react'
import { SAMPLE_COURSE_TITLES } from '../data/ontology'

const DEBOUNCE_MS = 250

export interface CourseSearchResult {
  title: string
  score: number
}

interface CourseSearchState {
  results: CourseSearchResult[]
  loading: boolean
  /** True when results come from the offline sample, not a live search. */
  offline: boolean
}

/**
 * Accent-fold a Greek (or any) string for comparison: NFD-decompose so tone
 * marks become separate code points, then strip them and lowercase.
 * Mirrors the backend's `normalize_greek` (app/grounding/normalize.py) so
 * this offline fallback behaves the same way the real search does — an
 * unaccented query like "δικτυα" must still match "Δίκτυα Υπολογιστών".
 */
function foldGreek(s: string): string {
  // \p{M} = Unicode general category "Mark" — every combining diacritic
  // (Greek tone marks included) in one property escape, no raw glyphs
  // needed in source. Requires the /u flag.
  return s.normalize('NFD').replace(/\p{M}/gu, '').toLowerCase()
}

function searchSampleTitles(query: string): CourseSearchResult[] {
  const q = foldGreek(query.trim())
  if (!q) return SAMPLE_COURSE_TITLES.map(title => ({ title, score: 1 }))
  return SAMPLE_COURSE_TITLES
    .filter(title => foldGreek(title).includes(q))
    .map(title => ({ title, score: 1 }))
}

export function useCourseSearch(query: string): CourseSearchState {
  const [state, setState] = useState<CourseSearchState>({
    results: searchSampleTitles(''),
    loading: false,
    offline: import.meta.env.VITE_USE_MOCK_API === '1',
  })

  // Tracks the most recently issued request so a slow earlier response
  // can't overwrite a faster later one (classic debounce race).
  const requestId = useRef(0)

  useEffect(() => {
    if (import.meta.env.VITE_USE_MOCK_API === '1') {
      setState({ results: searchSampleTitles(query), loading: false, offline: true })
      return
    }

    const thisRequest = ++requestId.current
    setState(prev => ({ ...prev, loading: true }))

    const handle = setTimeout(() => {
      const params = new URLSearchParams({ q: query || ' ', class: 'course', limit: '50' })
      fetch(`/entities/search?${params}`)
        .then(res => {
          if (!res.ok) throw new Error(`search failed: ${res.status}`)
          return res.json() as Promise<{ results: CourseSearchResult[] }>
        })
        .then(data => {
          if (requestId.current !== thisRequest) return // stale response, ignore
          setState({ results: data.results, loading: false, offline: false })
        })
        .catch(() => {
          if (requestId.current !== thisRequest) return
          setState({ results: searchSampleTitles(query), loading: false, offline: true })
        })
    }, DEBOUNCE_MS)

    return () => clearTimeout(handle)
  }, [query])

  return state
}
