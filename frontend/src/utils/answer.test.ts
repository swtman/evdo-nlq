import { describe, it, expect } from 'vitest'
import { booleanAnswerText, isBooleanResult } from './answer'

// ADR-037: an ASK (yes/no) query's answer arrives as `boolean` next to a one-row `answer` table.

describe('booleanAnswerText', () => {
  it('says «Ναι» for true and «Όχι» for false', () => {
    expect(booleanAnswerText(true)).toBe('Ναι')
    expect(booleanAnswerText(false)).toBe('Όχι')
  })
})

describe('isBooleanResult', () => {
  it('is true only for a real true/false answer', () => {
    expect(isBooleanResult(true)).toBe(true)
    expect(isBooleanResult(false)).toBe(true)
  })

  it('is false for SELECT results (null) and old history entries (undefined)', () => {
    expect(isBooleanResult(null)).toBe(false)
    expect(isBooleanResult(undefined)).toBe(false)
  })
})
