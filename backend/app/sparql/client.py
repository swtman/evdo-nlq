"""SPARQL client for EvdoGraph's GraphDB endpoint.

validate_sparql() uses rdflib for offline parse checking (no network).
SparqlClient.execute() makes a live HTTP call to GraphDB.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from SPARQLWrapper import JSON, SPARQLWrapper

logger = logging.getLogger(__name__)


@dataclass
class SparqlResult:
    columns: list[str]
    rows: list[dict[str, Any]]


def validate_sparql(query: str) -> str | None:
    """Return a parse error string if the query is invalid, or None if valid."""
    from rdflib.plugins.sparql.parser import parseQuery

    try:
        parseQuery(query)
        return None
    except Exception as exc:
        return str(exc)


class SparqlClient:
    """HTTP client for a SPARQL 1.1 endpoint (read-only)."""

    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint

    def execute(self, query: str) -> SparqlResult:
        """Execute a SELECT query and return structured results."""
        wrapper = SPARQLWrapper(self._endpoint)
        wrapper.setQuery(query)
        wrapper.setReturnFormat(JSON)
        try:
            raw = wrapper.query().convert()
        except Exception as exc:
            logger.error("SPARQL execution failed: %s", exc)
            raise RuntimeError(f"SPARQL execution failed: {exc}") from exc

        columns: list[str] = raw.get("head", {}).get("vars", [])
        bindings: list[dict] = raw.get("results", {}).get("bindings", [])
        rows = [
            {col: b[col]["value"] if col in b else None for col in columns}
            for b in bindings
        ]
        return SparqlResult(columns=columns, rows=rows)
