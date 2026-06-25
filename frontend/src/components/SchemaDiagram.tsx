/**
 * SchemaDiagram — hero diagram for the ΟΝΤΟΛΟΓΙΑ page.
 *
 * Approved design (brainstorming, 2026-06): merged Options A + B.
 * Layout: AcademicEntity frame (University ⇄ Department), cross-group edge,
 * LearningEntity frame (Course ⇄ Book), cross-group edge, dashed EvdoxusEntity
 * frame (Publisher). Inner edges are muted grey; cross-group edges use the
 * emerald accent. Each edge carries a property-name chip. Faint grid background.
 * Hover lifts each node (accent border). Scrolls horizontally on narrow screens.
 *
 * Data source: src/data/ontology.ts (no fetch, no SPARQL).
 */

import { classes, superclasses, relationships, totals } from '../data/ontology'
import { t } from '../i18n/el'

/** Resolve the formatted count for a class id */
function countFor(id: string): string {
  return classes.find(c => c.id === id)?.countFormatted ?? '?'
}

/** Resolve the formatted count for a superclass id */
function superCount(id: string): string {
  return superclasses.find(s => s.id === id)?.countFormatted ?? '?'
}

/** The academic group: University ⇄ Department */
function AcademicGroup() {
  const rel = relationships.find(r => r.from === 'University')!
  return (
    <div className="od-group od-group--solid" aria-label="AcademicEntity superclass">
      <span className="od-group-tab">
        AcademicEntity · {superCount('AcademicEntity')}
      </span>
      <div className="od-node" tabIndex={0} aria-label={`University ${countFor('University')} instances`}>
        <div className="od-node-name">University</div>
        <div className="od-node-greek">Πανεπιστήμιο</div>
        <div className="od-node-count">{countFor('University')}</div>
      </div>
      <div className="od-edge od-edge--inner" aria-hidden="true">
        <span className="od-prop">{rel.property}</span>
        <span className="od-arrow">⇄</span>
        <span className="od-prop">{rel.inverse}</span>
      </div>
      <div className="od-node" tabIndex={0} aria-label={`Department ${countFor('Department')} instances`}>
        <div className="od-node-name">Department</div>
        <div className="od-node-greek">Τμήμα</div>
        <div className="od-node-count">{countFor('Department')}</div>
      </div>
    </div>
  )
}

/** The learning group: Course ⇄ Book */
function LearningGroup() {
  const rel = relationships.find(r => r.from === 'Course')!
  return (
    <div className="od-group od-group--solid" aria-label="LearningEntity superclass">
      <span className="od-group-tab">
        LearningEntity · {superCount('LearningEntity')}
      </span>
      <div className="od-node" tabIndex={0} aria-label={`Course ${countFor('Course')} instances`}>
        <div className="od-node-name">Course</div>
        <div className="od-node-greek">Μάθημα</div>
        <div className="od-node-count">{countFor('Course')}</div>
      </div>
      <div className="od-edge od-edge--inner" aria-hidden="true">
        <span className="od-prop">{rel.property}</span>
        <span className="od-arrow">⇄</span>
        <span className="od-prop">{rel.inverse}</span>
      </div>
      <div className="od-node" tabIndex={0} aria-label={`Book ${countFor('Book')} instances`}>
        <div className="od-node-name">Book</div>
        <div className="od-node-greek">Βιβλίο</div>
        <div className="od-node-count">{countFor('Book')}</div>
      </div>
    </div>
  )
}

/** The publisher solo node in a dashed EvdoxusEntity frame */
function PublisherGroup() {
  return (
    <div className="od-group od-group--dashed" aria-label="EvdoxusEntity superclass (Publisher)">
      <span className="od-group-tab od-group-tab--faint">EvdoxusEntity</span>
      <div className="od-node" tabIndex={0} aria-label={`Publisher ${countFor('Publisher')} instances`}>
        <div className="od-node-name">Publisher</div>
        <div className="od-node-greek">Εκδότης</div>
        <div className="od-node-count">{countFor('Publisher')}</div>
      </div>
    </div>
  )
}

/** Cross-group edge between two groups */
function CrossEdge({ property, inverse }: { property: string; inverse: string }) {
  return (
    <div className="od-edge od-edge--cross" aria-hidden="true">
      <span className="od-prop">{property}</span>
      <span className="od-arrow">⇄</span>
      <span className="od-prop">{inverse}</span>
    </div>
  )
}

export function SchemaDiagram() {
  const deptToCourse = relationships.find(r => r.from === 'Department')!
  const bookToPublisher = relationships.find(r => r.from === 'Book')!


  return (
    <section className="od-diagram-wrap" aria-label="Διάγραμμα σχήματος EvdoGraph">
      {/* Faint grid canvas */}
      <div className="od-canvas" role="img" aria-label="Σχηματικό διάγραμμα κλάσεων EvdoGraph">
        {/* Caption */}
        <div className="od-caption">
          <span className="od-caption-eyebrow">Δομή γράφου · EvdoGraph</span>
          <span className="od-caption-snap">
            {t.ontologyStatEntities(totals.entitiesFormatted)} ·{' '}
            {t.ontologyDiagramCaption(totals.snapshot)}
          </span>
        </div>

        {/* Flow row */}
        <div className="od-flow">
          <AcademicGroup />
          <CrossEdge property={deptToCourse.property} inverse={deptToCourse.inverse} />
          <LearningGroup />
          <CrossEdge property={bookToPublisher.property} inverse={bookToPublisher.inverse} />
          <PublisherGroup />
        </div>

        {/* Legend */}
        <div className="od-legend" aria-label="Υπόμνημα διαγράμματος">
          <span className="od-legend-item">
            <span className="od-legend-swatch od-legend-swatch--accent">⇄</span>
            <span>{t.ontologyDiagramLegend1}</span>
          </span>
          <span className="od-legend-item">
            <span className="od-legend-swatch od-legend-swatch--border">▢</span>
            <span>{t.ontologyDiagramLegend2}</span>
          </span>
          <span className="od-legend-item">
            <span className="od-legend-swatch od-legend-swatch--faint">123</span>
            <span>{t.ontologyDiagramLegend3}</span>
          </span>
        </div>
      </div>
    </section>
  )
}
