/**
 * ExportMenu — dropdown that downloads the full result set in one of four formats.
 *
 * Always exports ALL rows (not just the current page) so the download is complete
 * regardless of how pagination is set. The FORMATS array is the single place to
 * add a new export format — no other file needs changing in this component.
 */

import { t } from '../../i18n/el'
import { toCSV, toJSON, toXML, toTSV, downloadBlob } from '../../utils/exporters'

type Row = Record<string, string | undefined>

type Props = {
  columns: string[]
  rows: Row[] // the full unfiltered/unpaginated result set
}

type Format = { key: 'csv' | 'json' | 'xml' | 'tsv'; label: string; desc: string }

// Declarative list of formats. Adding a new one only requires adding an entry here
// (plus a serialiser in exporters.ts and a label in i18n/el.ts).
const FORMATS: Format[] = [
  { key: 'csv',  label: t.exportCsv,  desc: t.exportCsvDesc  },
  { key: 'json', label: t.exportJson, desc: t.exportJsonDesc  },
  { key: 'xml',  label: t.exportXml,  desc: t.exportXmlDesc  },
  { key: 'tsv',  label: t.exportTsv,  desc: t.exportTsvDesc  },
]

// Maps format keys to the matching serialiser function from exporters.ts.
const SERIALIZERS = { csv: toCSV, json: toJSON, xml: toXML, tsv: toTSV }

export function ExportMenu({ columns, rows }: Props) {
  const handleExport = (fmt: Format['key']) => {
    const content = SERIALIZERS[fmt](columns, rows)
    downloadBlob(content, fmt) // triggers the browser's file-save dialog
  }

  return (
    <div className="dropdown-menu" role="menu" aria-label={t.exportLabel}>
      <div className="dropdown-header">{t.exportAllRows}</div>
      {FORMATS.map(fmt => (
        <div
          key={fmt.key}
          className="dropdown-item"
          role="menuitem"
          tabIndex={0}
          onClick={() => handleExport(fmt.key)}
          onKeyDown={e => e.key === 'Enter' && handleExport(fmt.key)}
        >
          <span>
            <span className="item-ext">{fmt.label}</span>
            {fmt.desc}
          </span>
          {/* Show total row count so the user knows how many rows they'll get. */}
          <span className="item-badge">{rows.length} rows</span>
        </div>
      ))}
    </div>
  )
}
