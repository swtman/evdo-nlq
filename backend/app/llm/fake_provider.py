"""FakeProvider — returns canned SPARQL with no network calls.

Use this for all unit tests and frontend development to avoid burning API tokens.
"""

from __future__ import annotations

from typing import Iterator

from app.llm.base import LLMResponse

_CANNED_SPARQL = (
    "PREFIX evdx: <https://w3id.org/evdoxus#>\n"
    "SELECT DISTINCT ?title WHERE {\n"
    "  ?book a evdx:Book ;\n"
    "        evdx:title ?title .\n"
    "}\n"
    "LIMIT 10"
)


class FakeProvider:
    """No-network LLMProvider for tests and frontend development."""

    def generate(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse:
        return LLMResponse(
            text=_CANNED_SPARQL,
            input_tokens=42,
            output_tokens=len(_CANNED_SPARQL.split()),
        )

    def stream(self, system: str, user: str, *, max_tokens: int = 1024) -> Iterator[str]:
        """Yield the canned SPARQL one character at a time to simulate streaming."""
        yield from _CANNED_SPARQL
