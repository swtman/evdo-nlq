/**
 * Pure serialisation helpers for downloading query results.
 * Each function takes the same (columns, rows) shape and returns a string.
 * Call downloadBlob() to turn any string into a browser file-download.
 */

type Row = Record<string, string | undefined>

/**
 * Wrap a CSV cell in double-quotes if it contains commas, quotes, or newlines.
 * Internal double-quotes are escaped by doubling them (""), per RFC 4180.
 */
function escapeCSV(v: string): string {
  if (v.includes(',') || v.includes('"') || v.includes('\n')) {
    return `"${v.replace(/"/g, '""')}"`
  }
  return v
}

/** Build a sortable timestamp string safe for use in filenames (no colons or dots). */
function timestamp(): string {
  return new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19)
}

/** Comma-separated values, RFC 4180 with \r\n row separators (Excel-compatible). */
export function toCSV(columns: string[], rows: Row[]): string {
  const header = columns.map(escapeCSV).join(',')
  const body = rows.map(row =>
    columns.map(col => escapeCSV(row[col] ?? '')).join(',')
  )
  // RFC 4180 requires \r\n line endings so Excel opens the file correctly.
  return [header, ...body].join('\r\n')
}

/** Pretty-printed JSON array where each element is one row as a plain object. */
export function toJSON(columns: string[], rows: Row[]): string {
  const data = rows.map(row =>
    Object.fromEntries(columns.map(col => [col, row[col] ?? '']))
  )
  return JSON.stringify(data, null, 2)
}

/** Escape a string for safe embedding in an XML attribute value (double-quoted). */
function escapeXMLAttr(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

/**
 * W3C SPARQL Query Results XML Format.
 * Uses the standard namespace so the file can be consumed by SPARQL tooling.
 * Special XML characters in cell values and column names are escaped.
 */
export function toXML(columns: string[], rows: Row[]): string {
  const vars = columns.map(c => `  <variable name="${escapeXMLAttr(c)}"/>`).join('\n')
  const results = rows.map(row => {
    const bindings = columns
      .map(col => {
        const val = (row[col] ?? '')
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
        return `      <binding name="${escapeXMLAttr(col)}"><literal>${val}</literal></binding>`
      })
      .join('\n')
    return `    <result>\n${bindings}\n    </result>`
  }).join('\n')
  return `<?xml version="1.0" encoding="UTF-8"?>
<sparql xmlns="http://www.w3.org/2005/sparql-results#">
  <head>\n${vars}\n  </head>
  <results>\n${results}\n  </results>
</sparql>`
}

/** Tab-separated values. Tabs and newlines inside cell values are replaced with spaces. */
export function toTSV(columns: string[], rows: Row[]): string {
  const header = columns.join('\t')
  const body = rows.map(row =>
    columns.map(col => (row[col] ?? '').replace(/\t/g, ' ').replace(/\n/g, ' ')).join('\t')
  )
  return [header, ...body].join('\n')
}

/**
 * Trigger a browser file download without navigating away from the page.
 *
 * How it works: create a Blob URL, attach it to a hidden <a> tag, click it
 * programmatically, then immediately clean up both the element and the URL.
 */
export function downloadBlob(content: string, ext: 'csv' | 'json' | 'xml' | 'tsv'): void {
  const mimeTypes = {
    csv: 'text/csv;charset=utf-8;',
    json: 'application/json',
    xml: 'application/xml',
    tsv: 'text/tab-separated-values;charset=utf-8;',
  }
  const blob = new Blob([content], { type: mimeTypes[ext] })
  const url = URL.createObjectURL(blob) // temporary blob: URL, only valid in this session
  const a = document.createElement('a')
  a.href = url
  a.download = `evdograph-results-${timestamp()}.${ext}`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url) // release memory immediately after the click
}
