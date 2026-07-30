/**
 * OntologyPage — static informational page about the EvdoGraph ontology.
 *
 * Sections (approved layout, 2026-06 brainstorming):
 *   1. Intro header — eyebrow + title + lead text + stat line
 *   2. SchemaDiagram — hero merged figure (AcademicEntity/LearningEntity frames)
 *   3. Class reference cards — responsive auto-fit grid, one card per class
 *   4. Relationships table — 4 object properties with inverses
 *   5. EntitySpotlights — searchable universities + departments + sample books
 *
 * Data: entirely static from src/data/ontology.ts and src/data/entities.json.
 * No backend calls, no SPARQL construction (display-only per CLAUDE.md).
 */

import { useState } from 'react'
import { classes, relationships, totals, exampleNodes, type ExampleNode } from '../data/ontology'
import { t } from '../i18n/el'
import { SchemaDiagram } from './SchemaDiagram'
import { EntitySpotlights } from './EntitySpotlights'
import { EntityModal } from './EntityModal'

// ── Section label with count badge ───────────────────────────────────────────

function SectionLabel({ label, count }: { label: string; count?: number | string }) {
  return (
    <div className="od-section-label" aria-hidden="true">
      <span>{label}</span>
      {/* {count !== undefined && <span className="od-section-count">{count}</span>} */}
    </div>
  )
}

// ── Generic example-node modal content ───────────────────────────────────────

/** Renders a refs array as accent chips; shows first N real refs + '…' overflow marker. */
function RefsField({ values }: { values: string[] }) {
  const real = values.filter(v => v !== '…')
  const overflow = values.includes('…')
  return (
    <span className="od-book-ex-kw">
      {real.map(v => (
        <span key={v} className="od-book-ex-ref od-ref-chip">{v}</span>
      ))}
      {overflow && <span className="od-ref-overflow">…</span>}
    </span>
  )
}

function ExampleNodeContent({ node }: { node: ExampleNode }) {
  return (
    <>
      <div className="od-book-ex-header">
        {node.image && (
          <img
            src={node.image}
            alt={node.heading}
            className="od-book-ex-img"
            onError={e => { (e.currentTarget as HTMLImageElement).style.display = 'none' }}
          />
        )}
        <div className="od-book-ex-meta">
          <div className="od-book-ex-title">{node.heading}</div>
          {node.subtitle && (
            <div className="od-book-ex-subtitle">{node.subtitle}</div>
          )}
          <div className="od-book-ex-code">evdx:ID · {node.id}</div>
        </div>
      </div>
      <dl className="od-book-ex-props">
        {node.fields.map(field => {
          const kind = field.kind ?? 'literal'
          return (
            <>
              <dt key={`dt-${field.prop}`}>{field.prop}</dt>
              <dd key={`dd-${field.prop}`}>
                {kind === 'keywords' && Array.isArray(field.value) && (
                  <span className="od-book-ex-kw">
                    {field.value.map(kw => (
                      <span key={kw} className="od-kw-chip">{kw}</span>
                    ))}
                  </span>
                )}
                {kind === 'refs' && Array.isArray(field.value) && (
                  <RefsField values={field.value} />
                )}
                {kind === 'ref' && typeof field.value === 'string' && (
                  <span className="od-book-ex-ref">{field.value}</span>
                )}
                {kind === 'link' && typeof field.value === 'string' && (
                  <a
                    href={field.value}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="od-book-ex-link"
                  >
                    {field.display ?? field.value}
                  </a>
                )}
                {kind === 'literal' && String(field.value)}
              </dd>
            </>
          )
        })}
      </dl>
    </>
  )
}

// ── Class card ────────────────────────────────────────────────────────────────

function ClassCard({ id }: { id: string }) {
  const cls = classes.find(c => c.id === id)
  const [modalOpen, setModalOpen] = useState(false)
  if (!cls) return null

  const exNode = exampleNodes[cls.id]

  return (
    <article className="od-class-card" aria-label={`Κλάση ${cls.name}`}>
      <div className="od-class-card-top">
        <div>
          <span className="od-class-name">{cls.name}</span>
          <span className="od-class-greek"> {cls.greek}</span>
        </div>
        <span className="od-class-count">{cls.countFormatted}</span>
      </div>
      <p className="od-class-desc">{cls.description}</p>
      <div className="od-class-chips" aria-label="Κύριες ιδιότητες">
        {cls.properties.map(p => (
          <span key={p} className="od-chip">{p}</span>
        ))}
      </div>
      <div className="od-class-example">
        {exNode ? (
          <button
            className="od-class-example-btn"
            type="button"
            onClick={() => setModalOpen(true)}
          >
            {t.ontologyBookExampleBtn} ↗
          </button>
        ) : (
          <>
            <span className="od-class-example-label">π.χ.&nbsp;</span>
            <span className="od-class-example-value">«{cls.example}»</span>
          </>
        )}
      </div>

      {modalOpen && exNode && (
        <EntityModal
          title={t.ontologyExampleTitle(cls.name)}
          onClose={() => setModalOpen(false)}
        >
          <ExampleNodeContent node={exNode} />
        </EntityModal>
      )}
    </article>
  )
}

// ── Relationships table ───────────────────────────────────────────────────────

function RelationshipsTable() {
  return (
    <div className="od-table-wrap">
      <table className="od-rels-table">
        <thead>
          <tr>
            <th scope="col">{t.ontologyRelFrom}</th>
            <th scope="col">{t.ontologyRelProp}</th>
            <th scope="col">{t.ontologyRelTo}</th>
            <th scope="col">{t.ontologyRelInverse}</th>
          </tr>
        </thead>
        <tbody>
          {relationships.map(rel => (
            <tr key={rel.property}>
              <td>{rel.from}</td>
              <td><span className="od-rel-prop">{rel.property}</span></td>
              <td>{rel.to}</td>
              <td><span className="od-rel-inv">{rel.inverse}</span></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function OntologyPage() {
  return (
    <main className="od-page" aria-label={t.ontologyTitle}>

      {/* ── Intro header ── */}
      <section className="od-intro" aria-labelledby="od-title">
        <p className="od-eyebrow">{t.ontologyEyebrow}</p>
        <h1 id="od-title" className="od-title">{t.ontologyTitle}</h1>
        <p className="od-lead">{t.ontologyLead}</p>
        <div className="od-statline" aria-label="Στατιστικά γράφου">
          <span><strong>{totals.classes}</strong> κλάσεις</span>
          <span className="od-dot" aria-hidden="true">·</span>
          <span><strong>{totals.relationships}</strong> σχέσεις</span>
          <span className="od-dot" aria-hidden="true">·</span>
          <span><strong>{totals.entitiesFormatted}</strong> οντότητες</span>
          <span className="od-dot" aria-hidden="true">·</span>
          <span><strong>{totals.booksFormatted}</strong> βιβλία</span>
        </div>
      </section>

      {/* ── Schema diagram ── */}
      <section className="od-section" aria-labelledby="od-sec-diagram">
        <SectionLabel label={t.ontologySectionDiagram} />
        <div id="od-sec-diagram" className="sr-only">{t.ontologySectionDiagram}</div>
        <SchemaDiagram />
      </section>

      {/* ── Class cards ── */}
      <section className="od-section" aria-labelledby="od-sec-classes">
        <SectionLabel label={t.ontologySectionClasses} count={totals.classes} />
        <div id="od-sec-classes" className="sr-only">{t.ontologySectionClasses}</div>
        <div className="od-class-grid">
          {classes.map(c => (
            <ClassCard key={c.id} id={c.id} />
          ))}
        </div>
      </section>

      {/* ── Relationships table ── */}
      <section className="od-section" aria-labelledby="od-sec-rels">
        <SectionLabel label={t.ontologySectionRels} count={totals.relationships} />
        <div id="od-sec-rels" className="sr-only">{t.ontologySectionRels}</div>
        <RelationshipsTable />
      </section>

      {/* ── Entity spotlights ── */}
      <section className="od-section" aria-labelledby="od-sec-entities">
        <SectionLabel label={t.ontologySectionEntities} />
        <div id="od-sec-entities" className="sr-only">{t.ontologySectionEntities}</div>
        <EntitySpotlights />
      </section>

    </main>
  )
}
