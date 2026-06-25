/**
 * highlightSparql — lightweight display-only SPARQL syntax highlighter.
 *
 * Tokenizes a SPARQL string into typed spans that map to the Console theme's
 * CSS variables:
 *   --kw   (green)  : SPARQL keywords (SELECT, WHERE, PREFIX, FILTER, etc.)
 *   --var  (blue)   : variables (?name)
 *   --str  (orange) : string literals ("…") and IRI references (<…>)
 *   --pre  (gray)   : prefix-qualified names (prefix:localName)
 *   plain           : everything else (punctuation, numbers, whitespace)
 *
 * Returns an array of {text, cls} token objects. `cls` is one of:
 *   'kw' | 'var' | 'str' | 'pre' | '' (plain)
 *
 * IMPORTANT: this function is display-only. It NEVER alters the SPARQL string —
 * it only wraps segments in class names for rendering. The string fed to the
 * backend is always the original unmodified value. (See CLAUDE.md: "Don't parse
 * or transform SPARQL — display-only".)
 */

export type SparqlToken = {
  text: string
  cls: 'kw' | 'var' | 'str' | 'pre' | ''
}

// Full list of SPARQL 1.1 keywords (case-insensitive match).
const KEYWORDS = new Set([
  'BASE', 'PREFIX', 'SELECT', 'CONSTRUCT', 'DESCRIBE', 'ASK',
  'ORDER', 'BY', 'LIMIT', 'OFFSET', 'DISTINCT', 'REDUCED',
  'FROM', 'NAMED', 'WHERE', 'GRAPH', 'OPTIONAL', 'UNION', 'MINUS',
  'FILTER', 'VALUES', 'BIND', 'AS', 'SERVICE', 'SILENT',
  'EXISTS', 'NOT', 'IN', 'GROUP', 'HAVING',
  // Aggregate functions
  'COUNT', 'SUM', 'MIN', 'MAX', 'AVG', 'SAMPLE', 'GROUP_CONCAT',
  // Test functions
  'BOUND', 'ISIRI', 'ISURI', 'ISBLANK', 'ISLITERAL', 'ISNUMERIC',
  'STR', 'LANG', 'DATATYPE', 'IRI', 'URI', 'BNODE', 'RAND',
  'ABS', 'CEIL', 'FLOOR', 'ROUND', 'CONCAT', 'STRLEN', 'UCASE', 'LCASE',
  'ENCODE_FOR_URI', 'CONTAINS', 'STRSTARTS', 'STRENDS', 'STRBEFORE', 'STRAFTER',
  'YEAR', 'MONTH', 'DAY', 'HOURS', 'MINUTES', 'SECONDS', 'TIMEZONE', 'TZ',
  'NOW', 'UUID', 'STRUUID', 'MD5', 'SHA1', 'SHA256', 'SHA384', 'SHA512',
  'COALESCE', 'IF', 'STRLANG', 'STRDT', 'LANGMATCHES', 'REGEX', 'REPLACE',
  'SEPARATOR', 'SUBSTR', 'true', 'false', 'a',
])

/**
 * Tokenize `sparql` into an array of typed tokens suitable for rendering.
 */
export function highlightSparql(sparql: string): SparqlToken[] {
  const tokens: SparqlToken[] = []
  let i = 0
  const n = sparql.length

  while (i < n) {
    // ── Comment (# until end of line) ──────────────────────────────────
    if (sparql[i] === '#') {
      const end = sparql.indexOf('\n', i)
      const text = end === -1 ? sparql.slice(i) : sparql.slice(i, end)
      tokens.push({ text, cls: 'pre' })
      i += text.length
      continue
    }

    // ── IRI reference <…> ──────────────────────────────────────────────
    if (sparql[i] === '<') {
      const end = sparql.indexOf('>', i + 1)
      if (end !== -1) {
        tokens.push({ text: sparql.slice(i, end + 1), cls: 'str' })
        i = end + 1
        continue
      }
    }

    // ── String literal "…" (simple, single-line) ───────────────────────
    if (sparql[i] === '"') {
      let j = i + 1
      while (j < n && sparql[j] !== '"' && sparql[j] !== '\n') {
        if (sparql[j] === '\\') j++ // skip escaped char
        j++
      }
      const end = j < n && sparql[j] === '"' ? j + 1 : j
      tokens.push({ text: sparql.slice(i, end), cls: 'str' })
      i = end
      continue
    }

    // ── Single-quoted string '…' ────────────────────────────────────────
    if (sparql[i] === "'") {
      let j = i + 1
      while (j < n && sparql[j] !== "'" && sparql[j] !== '\n') {
        if (sparql[j] === '\\') j++
        j++
      }
      const end = j < n && sparql[j] === "'" ? j + 1 : j
      tokens.push({ text: sparql.slice(i, end), cls: 'str' })
      i = end
      continue
    }

    // ── Variable ?name or $name ─────────────────────────────────────────
    if ((sparql[i] === '?' || sparql[i] === '$') && i + 1 < n && /\w/.test(sparql[i + 1])) {
      let j = i + 1
      while (j < n && /[\w-￿]/.test(sparql[j])) j++
      tokens.push({ text: sparql.slice(i, j), cls: 'var' })
      i = j
      continue
    }

    // ── Keyword or prefix:localName or plain identifier ─────────────────
    if (/[A-Za-z_-￿]/.test(sparql[i])) {
      let j = i
      while (j < n && /[\w-￿]/.test(sparql[j])) j++
      const word = sparql.slice(i, j)

      // peek ahead for colon → prefix:localName
      if (sparql[j] === ':') {
        let k = j + 1
        while (k < n && /[\w-￿.]/.test(sparql[k])) k++
        tokens.push({ text: sparql.slice(i, k), cls: 'pre' })
        i = k
        continue
      }

      if (KEYWORDS.has(word.toUpperCase()) || KEYWORDS.has(word)) {
        tokens.push({ text: word, cls: 'kw' })
      } else {
        tokens.push({ text: word, cls: '' })
      }
      i = j
      continue
    }

    // ── Whitespace — emit as a single plain token ───────────────────────
    if (/\s/.test(sparql[i])) {
      let j = i
      // collect consecutive whitespace, but keep newlines separate to preserve line structure
      if (sparql[i] === '\n') {
        tokens.push({ text: '\n', cls: '' })
        i++
      } else {
        while (j < n && sparql[j] !== '\n' && /\s/.test(sparql[j])) j++
        tokens.push({ text: sparql.slice(i, j), cls: '' })
        i = j
      }
      continue
    }

    // ── Everything else (punctuation, braces, operators) ────────────────
    tokens.push({ text: sparql[i], cls: '' })
    i++
  }

  return tokens
}
