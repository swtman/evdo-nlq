"""
FakeProvider — a pretend LLM that needs no internet connection.

WHEN TO USE IT
--------------
- All unit tests (pytest) use FakeProvider by default.
- Frontend UI development: set `VITE_USE_MOCK_API=1` in the frontend, which
  makes the React app talk to its own mock instead of the backend. But if you
  *do* run the backend during UI work, set `LLM_PROVIDER=fake` in `.env` so
  you still don't burn real API tokens.
- Any time you want to test the pipeline logic without caring about the SPARQL
  content itself.

"""

from __future__ import annotations

from app.llm.base import LLMResponse, StreamResult

# The hard-coded SPARQL query returned by every FakeProvider call.
# It is a valid (though trivial) query against the EvdoGraph ontology:
# "give me up to 10 book titles."
# Stored at module level so it is defined once and shared by both methods.
_CANNED_SPARQL = (
    "PREFIX evdx: <https://w3id.org/evdoxus#>\n"
    "SELECT DISTINCT ?title WHERE {\n"
    "  ?book a evdx:Book ;\n"
    "        evdx:title ?title .\n"
    "}\n"
    "LIMIT 10"
)


class FakeProvider:
    """A no-network implementation of the LLMProvider Protocol.

    Both methods ignore their arguments entirely — the same canned SPARQL is
    returned regardless of what `system` or `user` contain. That is fine
    because the goal is to test the pipeline *around* the LLM, not the LLM
    output itself.

    Because FakeProvider has `generate` and `stream` with the correct
    signatures, it automatically satisfies the `LLMProvider` Protocol without
    inheriting from anything.
    """

    def generate(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse:
        """Return the canned SPARQL as a complete response.

        Parameters (all ignored by this implementation)
        ----------
        system : str
            Would normally be the system prompt. Ignored here.
        user : str
            Would normally be the user's question. Ignored here.
        max_tokens : int
            Would normally cap output length. Ignored here.

        Returns
        -------
        LLMResponse
            `text` is the canned SPARQL string.
            `input_tokens` is a fixed placeholder (42) — no real prompt was
            sent, so there is no real token count.
            `output_tokens` is set to the word count of the canned SPARQL as
            a rough stand-in for a real count.
        """
        return LLMResponse(
            text=_CANNED_SPARQL,
            input_tokens=42,
            output_tokens=len(_CANNED_SPARQL.split()),
        )

    def stream(self, system: str, user: str, *, max_tokens: int = 1024) -> StreamResult:
        """Return the canned SPARQL delivered one character at a time.

        This mimics how a real streaming provider works: the pipeline iterates
        over `result.tokens` and forwards each piece to the frontend. Here,
        each "piece" is a single character of the canned SPARQL string.

        HOW `iter(resp.text)` WORKS
        ----------------------------
        In Python, calling `iter()` on a string turns it into an iterator that
        yields one character per step. For example:

            iter("hi!")  →  yields "h", then "i", then "!"

        So `iter(resp.text)` makes the pipeline believe it is receiving a live
        stream of tokens — it just happens that each token is one character,
        and the "stream" is already fully available in memory.

        Unlike real providers, token counts are set immediately (not deferred),
        because there is no background generator that needs to finish first.
        """
        resp = self.generate(system, user)
        return StreamResult(
            tokens=iter(resp.text),       # one character per iteration step
            input_tokens=resp.input_tokens,
            output_tokens=resp.output_tokens,
        )
