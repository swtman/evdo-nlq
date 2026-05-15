/**
 * useHistory — persists query history to localStorage and keeps it in React state.
 *
 * History survives page reloads. On every write the new array is immediately
 * serialised to localStorage so nothing is lost if the tab is closed.
 *
 * Cap: at most MAX_ENTRIES (20) items, newest first. When the cap is exceeded
 * the oldest entry is dropped automatically (FIFO).
 *
 * Usage:
 *   const { entries, addEntry, clearHistory } = useHistory()
 */

import { useState, useCallback } from 'react'
import type { HistoryEntry } from '../types'

const STORAGE_KEY = 'evdograph.history' // localStorage key
const MAX_ENTRIES = 20

/**
 * Read the history array from localStorage on mount.
 * Returns an empty array if the key is missing or the JSON is corrupt.
 * Passed directly as the useState initializer so it runs only once.
 */
function loadFromStorage(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return []
    return JSON.parse(raw) as HistoryEntry[]
  } catch {
    return [] // corrupt JSON — start fresh rather than crashing
  }
}

/** Write the current entries array to localStorage. Silently ignores quota errors. */
function saveToStorage(entries: HistoryEntry[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries))
  } catch {
    // localStorage quota exceeded (rare) — the in-memory state is still correct.
  }
}

// Omit 'id' and 'timestamp' from the input type because this hook generates them.
type AddEntryInput = Omit<HistoryEntry, 'id' | 'timestamp'>

export function useHistory() {
  // loadFromStorage is called once as the useState initializer (no useEffect needed).
  const [entries, setEntries] = useState<HistoryEntry[]>(loadFromStorage)

  const addEntry = useCallback((input: AddEntryInput) => {
    const entry: HistoryEntry = {
      ...input,
      id: crypto.randomUUID(), // stable React key and unique identifier
      timestamp: Date.now(),
    }
    setEntries(prev => {
      // Prepend the new entry, then cap the array length.
      const next = [entry, ...prev].slice(0, MAX_ENTRIES)
      saveToStorage(next)
      return next
    })
  }, [])

  const clearHistory = useCallback(() => {
    setEntries([])
    localStorage.removeItem(STORAGE_KEY)
  }, [])

  return { entries, addEntry, clearHistory }
}
