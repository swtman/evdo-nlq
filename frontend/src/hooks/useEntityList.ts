/**
 * useEntityList — one-shot exhaustive fetch against GET /entities/list.
 *
 * Backs the "δείτε τα όλα" browse modal on the University/Department
 * ΟΝΤΟΛΟΓΙΑ cards. This is a DIFFERENT operation from `useEntitySearch`: no
 * query phrase, no ranking, no debounce — just "give me everything in this
 * class, alphabetically" (see backend/app/api/entities.py's module
 * docstring "SCOPE" for why that's a separate endpoint rather than
 * `/entities/search`'s empty-query behaviour). Only `university` and
 * `department` are listable — course/book are far too large (see
 * `EntityClass` in useEntitySearch.ts and `LISTABLE_CLASSES` backend-side).
 *
 * Fetches once per mount (or per `entityClass` change) rather than on every
 * keystroke — the modal's own search box then filters the already-fetched
 * full list client-side, same UX the old bundled-entities.json cards had,
 * just backed by a live fetch instead of a bundled JSON import.
 *
 * Falls back to the same offline sample convention as `useEntitySearch`
 * (VITE_USE_MOCK_API=1, or a failed fetch) so the modal never silently shows
 * a truncated list without saying so.
 */

import { useEffect, useRef, useState } from 'react'
import type { EntitySearchResult } from './useEntitySearch'
import { SAMPLE_UNIVERSITY_TITLES, SAMPLE_DEPARTMENT_TITLES } from '../data/ontology'

export type ListableEntityClass = 'university' | 'department'

interface EntityListState {
  results: EntitySearchResult[]
  loading: boolean
  /** True when results come from the offline sample, not a live fetch. */
  offline: boolean
}

const SAMPLE_TITLES: Record<ListableEntityClass, string[]> = {
  university: SAMPLE_UNIVERSITY_TITLES,
  department: SAMPLE_DEPARTMENT_TITLES,
}

function sampleResults(entityClass: ListableEntityClass): EntitySearchResult[] {
  return SAMPLE_TITLES[entityClass].map(title => ({ title, score: 1, parents: [] }))
}

export function useEntityList(entityClass: ListableEntityClass): EntityListState {
  const [state, setState] = useState<EntityListState>({
    results: sampleResults(entityClass),
    loading: false,
    offline: import.meta.env.VITE_USE_MOCK_API === '1',
  })

  // Stale-response guard, same pattern as useEntitySearch — a slow earlier
  // fetch (e.g. a class switch mid-flight) can't overwrite a later one.
  const requestId = useRef(0)

  useEffect(() => {
    if (import.meta.env.VITE_USE_MOCK_API === '1') {
      setState({ results: sampleResults(entityClass), loading: false, offline: true })
      return
    }

    const thisRequest = ++requestId.current
    setState(prev => ({ ...prev, loading: true }))

    const params = new URLSearchParams({ class: entityClass, limit: '1000' })
    fetch(`/entities/list?${params}`)
      .then(res => {
        if (!res.ok) throw new Error(`list failed: ${res.status}`)
        return res.json() as Promise<{ results: EntitySearchResult[] }>
      })
      .then(data => {
        if (requestId.current !== thisRequest) return
        setState({ results: data.results, loading: false, offline: false })
      })
      .catch(() => {
        if (requestId.current !== thisRequest) return
        setState({ results: sampleResults(entityClass), loading: false, offline: true })
      })
  }, [entityClass])

  return state
}
