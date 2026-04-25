"""
explore_ontology.py — introspect the EvdoGraph ontology.

Runs a handful of metadata queries against the endpoint and writes a compact
summary that you can paste (or reference) into prompts. Also useful for
populating notes/ONTOLOGY-NOTES.md.

Usage:
    uv run python scripts/explore_ontology.py
    uv run python scripts/explore_ontology.py --output notes/ontology-summary.md

No API keys needed.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

try:
    from SPARQLWrapper import JSON, SPARQLWrapper
except ImportError:
    print("Install SPARQLWrapper first: uv add SPARQLWrapper", file=sys.stderr)
    sys.exit(2)


DEFAULT_ENDPOINT = "http://lod.csd.auth.gr:7200/repositories/Evdoxus"
PREFIXES = """
PREFIX evdx: <https://w3id.org/evdoxus#>
"""


def run(endpoint: str, query: str, timeout: int = 120) -> list[dict[str, Any]]:
    """Execute a SPARQL SELECT query and return the bindings list."""
    sparql = SPARQLWrapper(endpoint)
    sparql.setTimeout(timeout)
    sparql.setQuery(PREFIXES + query)
    sparql.setReturnFormat(JSON)
    result = sparql.queryAndConvert()  # type: ignore[assignment]
    return result["results"]["bindings"]


def classes(endpoint: str, limit: int = 100) -> list[dict[str, Any]]:
    """Return application classes ordered by instance count, excluding OWL/RDF/RDFS internals."""
    query = f"""
    SELECT ?class (COUNT(?s) AS ?count)
    WHERE {{
      ?s a ?class .
      FILTER(isIRI(?class))
      FILTER(!STRSTARTS(STR(?class), "http://www.w3.org/2002/07/owl#"))
      FILTER(!STRSTARTS(STR(?class), "http://www.w3.org/1999/02/22-rdf-syntax-ns#"))
      FILTER(!STRSTARTS(STR(?class), "http://www.w3.org/2000/01/rdf-schema#"))
    }}
    GROUP BY ?class
    ORDER BY DESC(?count)
    LIMIT {limit}
    """
    return run(endpoint, query)


def properties(endpoint: str, limit: int = 200) -> list[dict[str, Any]]:
    """Return evdoxus-namespaced properties ordered by usage count.

    Scanning all triples for GROUP BY causes OOM on large repositories, so we
    restrict to the evdx namespace before aggregating.
    """
    query = f"""
    SELECT ?p (COUNT(*) AS ?count)
    WHERE {{
      ?s ?p ?o .
      FILTER(STRSTARTS(STR(?p), "https://w3id.org/evdoxus#"))
    }}
    GROUP BY ?p
    ORDER BY DESC(?count)
    LIMIT {limit}
    """
    return run(endpoint, query)


def labels_for_class(endpoint: str, class_uri: str, limit: int = 5) -> list[dict[str, Any]]:
    """A few labelled instances of a class, for getting a feel for the data."""
    query = f"""
    SELECT ?s ?label
    WHERE {{
      ?s a <{class_uri}> .
      OPTIONAL {{ ?s <http://www.w3.org/2000/01/rdf-schema#label> ?label }}
    }}
    LIMIT {limit}
    """
    return run(endpoint, query)


def namespaces(endpoint: str) -> list[dict[str, Any]]:
    """Best-effort list of namespaces used in the graph."""
    # Regex captures everything up to and including the last # or / (the namespace delimiter).
    # Without the fix "(.*[/#])" the delimiter was consumed but not captured, producing
    # "http://example.org/schema" instead of the correct "http://example.org/schema#".
    query = """
    SELECT DISTINCT ?ns
    WHERE {
    {
        # Phase 1: Identify unique IRIs first
        SELECT DISTINCT ?iri WHERE {
        { 
            # Most engines use a Predicate Index to make this near-instant
            SELECT DISTINCT ?iri WHERE { ?s ?iri ?o } 
        }
        UNION
        { 
            # Identify unique classes
            SELECT DISTINCT ?iri WHERE { ?s a ?iri . FILTER(isIRI(?iri)) } 
        }
        }
    }
    # Phase 2: Run the expensive regex ONLY on the unique IRIs
    BIND(REPLACE(STR(?iri), "(.*[/#])[^/#]*$", "$1") AS ?ns)
    }
    LIMIT 50
    """
    return run(endpoint, query)


def format_summary(
    endpoint: str,
    class_rows: list[dict[str, Any]],
    property_rows: list[dict[str, Any]],
    ns_rows: list[dict[str, Any]],
    sample_rows: dict[str, list[dict[str, Any]]] | None = None,
) -> str:
    """Render query results as a Markdown report with namespace, class, and property tables."""
    lines: list[str] = []
    lines.append(f"# EvdoGraph ontology summary\n")
    lines.append(f"Endpoint: `{endpoint}`\n")

    lines.append("## Namespaces observed\n")
    for row in ns_rows:
        lines.append(f"- `{row['ns']['value']}`")
    lines.append("")

    lines.append("## Top classes (by instance count)\n")
    lines.append("| Class | Count | Sample labels |")
    lines.append("|---|---:|---|")
    for row in class_rows:
        cls_uri = row["class"]["value"]
        count = int(row["count"]["value"])
        samples = ""
        if sample_rows and cls_uri in sample_rows:
            labels = [
                r["label"]["value"] if "label" in r else r["s"]["value"].split("/")[-1]
                for r in sample_rows[cls_uri]
            ]
            samples = ", ".join(labels[:3])
        lines.append(f"| `{cls_uri}` | {count:,} | {samples} |")
    lines.append("")

    lines.append("## Top properties (by usage count)\n")
    lines.append("| Property | Count |")
    lines.append("|---|---:|")
    for row in property_rows:
        lines.append(f"| `{row['p']['value']}` | {int(row['count']['value']):,} |")
    lines.append("")

    lines.append("## Suggested prompt-friendly schema\n")
    lines.append(
        "_(A compact version of the above, suitable for pasting into the `{ontology_summary}` slot in `prompts/nl-to-sparql-v1.md`. Hand-curate this after exploring.)_\n"
    )
    lines.append("```turtle")
    lines.append("# TODO: fill in with the most useful ~20 classes and ~30 properties.")
    lines.append("# Keep the whole section under ~2000 tokens.")
    lines.append("```")
    return "\n".join(lines)


def main() -> int:
    """Parse CLI args, run all introspection queries, and print or write the Markdown summary."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--endpoint",
        default=os.environ.get("GRAPHDB_ENDPOINT", DEFAULT_ENDPOINT),
        help="SPARQL endpoint URL",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write summary to this file (Markdown). If omitted, print to stdout.",
    )
    parser.add_argument("--class-limit", type=int, default=50)
    parser.add_argument("--property-limit", type=int, default=100)
    args = parser.parse_args()

    print(f"Querying {args.endpoint} ...", file=sys.stderr)
    try:
        cls = classes(args.endpoint, args.class_limit)
        print("Classes OK")
        props = properties(args.endpoint, args.property_limit)
        print("Properties OK")
        ns = namespaces(args.endpoint)
        print("Namespaces OK")
        samples = {
            row["class"]["value"]: labels_for_class(args.endpoint, row["class"]["value"])
            for row in cls[:10]  # fetch samples for the 10 most populated classes only
        }
        print("Samples OK")
    except Exception as exc:
        print(f"Query failed: {exc}", file=sys.stderr)
        return 1

    summary = format_summary(args.endpoint, cls, props, ns, samples)

    if args.output:
        out_path = Path(args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(summary, encoding="utf-8")
        print(f"Wrote summary to {out_path}", file=sys.stderr)
    else:
        print(summary)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
