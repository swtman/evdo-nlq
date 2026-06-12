"""
sparql_hello.py — smoke test for the EvdoGraph endpoint.

This is the FIRST thing to run after cloning the repo. If this works, the rest
of the project has a real foundation. If it fails, fix that before anything else.

Usage:
    uv run python scripts/sparql_hello.py
    # or
    python scripts/sparql_hello.py

No API keys needed — this only talks to GraphDB, not the LLM.
"""

from __future__ import annotations

import os
import sys
from typing import Any

try:
    from SPARQLWrapper import JSON, SPARQLWrapper
except ImportError:
    print(
        "Missing dependency. Install with:\n"
        "    uv add SPARQLWrapper\n"
        "or:\n"
        "    pip install SPARQLWrapper\n",
        file=sys.stderr,
    )
    sys.exit(2)


DEFAULT_ENDPOINT = "http://lod.csd.auth.gr:7200/repositories/EvdoGraph"
# Prefixes every query will share. Declared once, prepended automatically.
PREFIXES = """
PREFIX evdx: <https://w3id.org/evdoxus#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
"""


def run_query(endpoint: str, query: str) -> tuple[list[dict] | None, str | None]:
    try:
        sparql = SPARQLWrapper(endpoint)
        sparql.setQuery(PREFIXES + query)
        sparql.setReturnFormat(JSON)
        sparql.setTimeout(10)  # Timeout after 10 seconds to avoid hanging
        result = sparql.queryAndConvert()  # type: ignore[return-value]
        return result, None
    except Exception as e:
        # Most server-side SPARQL errors come back as HTTPError with a
        # helpful message in the body. We capture that whole string.
        return None, f"{type(e).__name__}: {e}"



def main() -> int:
    endpoint = os.environ.get("GRAPHDB_ENDPOINT", DEFAULT_ENDPOINT)
    print(f"Endpoint: {endpoint}")

    # Query 1: "can you answer anything?"
    q1 = """
    SELECT (COUNT(*) AS ?triples) WHERE { ?s ?p ?o }
    """
    print("\n[1/3] Counting all triples (quick sanity)...")
    try:
        r, err = run_query(endpoint, q1)
        if err:
            print(f"      FAILED — {err}")
            print(
                "\nIf you see a connection error:\n"
                "  - Are you on the AUTh network or VPN?\n"
                "  - Try opening the endpoint in a browser to confirm it's up.\n"
                "  - Check the repository path.",
                file=sys.stderr,
            )
            return 1
        n = r["results"]["bindings"][0]["triples"]["value"]
        print(f"      OK — {int(n):,} triples in the store.")
    except Exception as exc:
        print(f"      FAILED — {exc}")
        print(
            "\nIf you see a connection error:\n"
            "  - Are you on the AUTh network or VPN?\n"
            "  - Try opening the endpoint in a browser to confirm it's up.\n"
            "  - Check the repository path ",
            file=sys.stderr,
        )
        return 1

    # Query 2: list the distinct classes present
    q2 = """
    SELECT ?class (COUNT(?s) AS ?count)
    WHERE { ?s a ?class }
    GROUP BY ?class
    ORDER BY DESC(?count)
    LIMIT 20
    """
    print("\n[2/3] Top 20 classes by instance count:")
    try:
        r, err = run_query(endpoint, q2)
        if err:
            print(f"      FAILED — {err}")
            return 1
        for row in r["results"]["bindings"]:
            cls = row["class"]["value"]
            count = row["count"]["value"]
            print(f"      {count:>8}  {cls}")
    except Exception as exc:
        print(f"      FAILED — {exc}")
        return 1


    print("All good. The endpoint is reachable and returning data.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
