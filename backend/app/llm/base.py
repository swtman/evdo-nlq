"""
Shared types for the LLM layer.

This file defines the "contract" that every LLM provider in this project must follow.
Instead of writing code that is tied to a specific AI service (Claude, Gemini, etc.),
the rest of the codebase talks only to the types defined here. That way, swapping one
provider for another never requires touching the pipeline or route code. You just
point the factory at a different class.

Three things live here:
  1. LLMResponse  — what you get back from a non-streaming (full-text) LLM call.
  2. StreamResult — what you get back from a streaming (token-by-token) LLM call.
  3. LLMProvider  — the interface (Protocol) every provider class must satisfy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Protocol, runtime_checkable

@dataclass
class LLMResponse:
    """The result of a single, non-streaming LLM call.

    Used when the pipeline asks the LLM for a complete answer all at once
    (as opposed to receiving it word-by-word). This happens during the retry
    loop, after the initial streaming attempt fails SPARQL validation, the
    pipeline switches to non-streaming for the correction attempts or when a user
    manually edits and/or resubmits a query to be executed against GraphDB.

    Fields
    ------
    text : str
        The full text the LLM produced. In this project that will be a SPARQL
        query (or the special string "# NOT_ANSWERABLE: ..." if the LLM could
        not answer the question).
    input_tokens : int
        How many tokens the prompt consumed. Tracked for cost awareness.
        This is 0 when the response was served from the disk cache.
    output_tokens : int
        How many tokens the LLM generated. Also 0 on a cache hit.
    """

    text: str
    input_tokens: int
    output_tokens: int


@dataclass
class StreamResult:
    """The result of a streaming LLM call.

    Instead of waiting for the full answer, streaming lets the pipeline forward
    each small chunk ("token") to the frontend as soon as it arrives, so the
    user can watch the SPARQL query appear character-by-character.

    How streaming works here
    ------------------------
    The provider returns a StreamResult immediately. At that point the LLM has
    not finished yet but it is still running. The actual text lives inside
    `tokens`, which is a lazy iterator.

    How 'tokens' are counted
    -----------------------------------------------------------
    `input_tokens` and `output_tokens` start at 0. The provider's internal
    generator updates them only after it yields the last token. So if you
    read those fields before draining `tokens` you will always get 0.

    The pipeline in query_pipeline.py handles this correctly: it exhausts the
    iterator in a loop, then reads the usage fields.

    Fields
    ------
    tokens : Iterator[str]
        A lazy sequence of text chunks. Iterate over it to receive the
        llm-generated text piece by piece.
    input_tokens : int
        Prompt token count — populated only after `tokens` is fully consumed.
        Defaults to 0.
    output_tokens : int
        Generated token count — same deferred behaviour as `input_tokens`.
        Defaults to 0.
    """

    tokens: Iterator[str]
    input_tokens: int = field(default=0)
    output_tokens: int = field(default=0)


@runtime_checkable
class LLMProvider(Protocol):
    """The interface every LLM provider class must satisfy.

    ClaudeProvider, GeminiProvider, OllamaProvider and FakeProvider all implement this
    interface without inheriting from it. They just define the same two
    methods with matching signatures, and Python's type checker accepts them.

    Methods
    -------
    generate(system, user, *, max_tokens) -> LLMResponse
        Ask the LLM for a complete answer and wait for it to finish.
        Used by the retry loop and the synchronous /query endpoint.

    stream(system, user, *, max_tokens) -> StreamResult
        Ask the LLM for an answer delivered token-by-token.
        Used for the initial SPARQL generation in /query/stream.

    Parameters shared by both methods
    ----------------------------------
    system : str
        The system prompt, the background instructions for the LLM.
        Contains the ontology summary and the NL-to-SPARQL prompt template and perhaps other context
        (e.g. some few-shot examples).
    user : str
        The user message, the natural-language question from the end user.
    max_tokens : int, keyword-only, default 1024
        Hard cap on how many tokens the LLM may generate. Keyword-only means
        callers must write `max_tokens=512`, not just pass `512` positionally.
        No call site in this project overrides the default, so 1024 is the
        effective limit for all SPARQL generation.
    """

    def generate(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse: ...

    def stream(self, system: str, user: str, *, max_tokens: int = 1024) -> StreamResult: ...
