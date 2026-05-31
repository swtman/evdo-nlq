import { describe, it, expect } from 'vitest'
import { toCSV, toJSON, toXML, toTSV } from './exporters'

// --- toXML ---

describe('toXML', () => {
  it('escapes double-quotes in column names (attribute injection guard)', () => {
    const xml = toXML(['col"name'], [])
    expect(xml).toContain('name="col&quot;name"')
    expect(xml).not.toContain('name="col"name"')
  })

  it('escapes angle brackets in column names', () => {
    const xml = toXML(['col<bad>name'], [])
    expect(xml).toContain('name="col&lt;bad&gt;name"')
  })

  it('escapes ampersands in column names', () => {
    const xml = toXML(['col&name'], [])
    expect(xml).toContain('name="col&amp;name"')
  })

  it('escapes column names in both <variable> and <binding> elements', () => {
    const col = 'x"y'
    const xml = toXML([col], [{ [col]: 'value' }])
    // <variable name="x&quot;y"/>
    expect(xml).toContain('<variable name="x&quot;y"/>')
    // <binding name="x&quot;y">
    expect(xml).toContain('<binding name="x&quot;y">')
  })

  it('still escapes special chars in cell values', () => {
    const xml = toXML(['title'], [{ title: '<Αλγόριθμοι & Δομές>' }])
    expect(xml).toContain('&lt;Αλγόριθμοι &amp; Δομές&gt;')
    expect(xml).not.toContain('<Αλγόριθμοι')
  })

  it('produces valid XML structure with normal column names', () => {
    const xml = toXML(['title', 'author'], [
      { title: 'Εισαγωγή', author: 'Παπαδόπουλος' },
    ])
    expect(xml).toContain('<?xml version="1.0"')
    expect(xml).toContain('<sparql xmlns=')
    expect(xml).toContain('<variable name="title"/>')
    expect(xml).toContain('<variable name="author"/>')
    expect(xml).toContain('<literal>Εισαγωγή</literal>')
  })

  it('handles empty rows', () => {
    const xml = toXML(['col1', 'col2'], [])
    expect(xml).toContain('<variable name="col1"/>')
    expect(xml).not.toContain('<result>')
  })
})

// --- toCSV ---

describe('toCSV', () => {
  it('wraps cells containing commas in double-quotes', () => {
    const csv = toCSV(['name'], [{ name: 'Αλγόριθμοι, Δομές' }])
    expect(csv).toContain('"Αλγόριθμοι, Δομές"')
  })

  it('escapes internal double-quotes by doubling them', () => {
    const csv = toCSV(['name'], [{ name: 'say "hello"' }])
    expect(csv).toContain('"say ""hello"""')
  })
})

// --- toJSON ---

describe('toJSON', () => {
  it('produces valid JSON with correct column values', () => {
    const json = toJSON(['title'], [{ title: 'Εισαγωγή' }])
    const parsed = JSON.parse(json)
    expect(parsed).toEqual([{ title: 'Εισαγωγή' }])
  })

  it('uses empty string for missing (undefined) cells', () => {
    const json = toJSON(['title', 'missing'], [{ title: 'Εισαγωγή' }])
    const parsed = JSON.parse(json)
    expect(parsed[0].missing).toBe('')
  })
})

// --- toTSV ---

describe('toTSV', () => {
  it('replaces embedded tabs in cell values with spaces', () => {
    const tsv = toTSV(['col'], [{ col: 'a\tb' }])
    const lines = tsv.split('\n')
    expect(lines[1]).toBe('a b')
  })
})
