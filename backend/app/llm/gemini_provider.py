"""
Google Gemini implementation of LLMProvider.

BOUNDARY RULE
-------------
Only this file may import `google.genai`. All other modules must interact with
LLMs through the `LLMProvider` Protocol in `base.py`.

HOW THIS FILE RELATES TO claude_provider.py
--------------------------------------------
The structure here is identical to ClaudeProvider,
the only differences are Gemini-SDK-specific.

Read the `claude_provider.py` documentation first — the concepts (generator,
closure, deferred population) are explained in detail there and are not
repeated here.
"""

from __future__ import annotations

import logging
from typing import Iterator

import google.genai as genai
from google.genai import types 

from app.llm.base import LLMResponse, StreamResult
from app.llm.cache import DiskCache

logger = logging.getLogger(__name__)


class GeminiProvider:
    """Google Gemini implementation. Wraps every call with a disk cache.

    Satisfies the `LLMProvider` Protocol through structural subtyping —
    no inheritance from `LLMProvider` is needed.
    """

    def __init__(self, model: str, api_key: str, cache: DiskCache) -> None:
        """Store the model name, create the Gemini client, and attach the cache.

        Parameters
        ----------
        model : str
            The Gemini model identifier, e.g. "gemini-2.5-flash-lite". Passed to
            every API call.
        api_key : str
            The Google secret key from `.env`. Never committed to git.
        cache : DiskCache
            The shared disk cache — checked before and written to after every
            real API call.
        """
        self._model = model
        self._client = genai.Client(api_key=api_key)
        self._cache = cache

    # ------------------------------------------------------------------
    # generate() — non-streaming path
    # ------------------------------------------------------------------

    def generate(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse:
        """Ask Gemini for a complete answer and wait for it to finish.

        The flow is the same as ClaudeProvider.generate():
          1. Cache check — return immediately if we've seen this prompt before.
          2. API call — `generate_content` blocks until Gemini finishes.
          3. Cache write — save the response for next time.
          4. Log token usage.
          5. Return LLMResponse.

        GEMINI-SPECIFIC DIFFERENCES FROM CLAUDE
        ----------------------------------------
        - The system prompt is passed inside a `GenerateContentConfig` object
          (as `system_instruction`) rather than as a top-level parameter.
        - The response text lives at `response.text` (a property, not
          `response.content[0].text`).
        - Both `response.text` and `response.usage_metadata` can be `None`
          if Gemini refuses the request or hits an internal error — we guard
          against both and raise a clear RuntimeError.
        - Token count fields use the names `prompt_token_count` (input) and
          `candidates_token_count` (output), and can themselves be `None`,
          so we fall back to 0 with the `or 0` pattern.

        Parameters
        ----------
        system : str
            The system prompt (ontology summary + NL-to-SPARQL template).
        user : str
            The user's natural-language question.
        max_tokens : int
            Hard cap on output length. Keyword-only.
        """
        # Step 1 — cache check
        cached = self._cache.get(system, user, self._model)
        if cached is not None:
            return LLMResponse(text=cached, input_tokens=0, output_tokens=0)

        # Step 2 — call the Gemini API (non-streaming)
        # `types.GenerateContentConfig` bundles optional settings together.
        # `system_instruction` is Gemini's name for the system prompt.
        response = self._client.models.generate_content(
            model=self._model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
            ),
        )

        # Guard: Gemini can return None for text (e.g. if the request was
        # blocked by safety filters). Raise early with a clear message.
        text = response.text
        if text is None:
            raise RuntimeError("Gemini returned no text content")

        # Guard: usage_metadata can also be None in edge cases.
        usage = response.usage_metadata
        if usage is None:
            raise RuntimeError("Gemini returned no usage metadata")

        # `or 0` handles the case where the count fields themselves are None.
        prompt_tokens = usage.prompt_token_count or 0
        candidate_tokens = usage.candidates_token_count or 0

        # Step 3 — cache write
        self._cache.set(system, user, self._model, text)

        # Step 4 — log usage
        logger.info(
            "Gemini [%s] input=%d output=%d",
            self._model,
            prompt_tokens,
            candidate_tokens,
        )

        # Step 5 — return
        return LLMResponse(
            text=text,
            input_tokens=prompt_tokens,
            output_tokens=candidate_tokens,
        )

    # ------------------------------------------------------------------
    # stream() — streaming path
    # ------------------------------------------------------------------

    def stream(self, system: str, user: str, *, max_tokens: int = 1024) -> StreamResult:
        """Return a StreamResult whose tokens iterator yields raw text chunks.

        The overall pattern is identical to ClaudeProvider.stream() — a
        generator closure `_gen()` that populates the StreamResult's usage
        fields after the last token is yielded (deferred population).

        KEY DIFFERENCE FROM CLAUDE'S STREAMING
        ----------------------------------------
        Claude's SDK provides a clean `.get_final_message()` call that returns
        usage only after the stream is fully consumed.

        Gemini's SDK includes usage metadata on individual chunks throughout
        the stream — but not every chunk carries it, and the counts accumulate
        as the stream progresses. The last chunk that contains `usage_metadata`
        has the final totals. So `_gen()` tracks the most recently seen
        `usage_metadata` in `last_usage` and reads the totals from it after
        the loop ends.

        If no chunk contained usage data at all (unexpected), a warning is
        logged and usage remains 0.

        For a full explanation of the generator / closure / deferred-population
        pattern, see the detailed comments in `claude_provider.py`.
        """
        result = StreamResult(tokens=iter([]))

        def _gen() -> Iterator[str]:
            # Cache check — same as Claude
            cached = self._cache.get(system, user, self._model)
            if cached is not None:
                yield cached
                return

            full_text = ""
            last_usage = None  # will hold the last chunk's usage_metadata

            # `generate_content_stream` returns an iterator of response chunks.
            # Each chunk may contain text, usage metadata, or both.
            for chunk in self._client.models.generate_content_stream(
                model=self._model,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=max_tokens,
                ),
            ):
                # A chunk may or may not carry text. Guard before using it.
                if chunk.text:
                    full_text += chunk.text
                    yield chunk.text  # forward to the pipeline

                # Keep updating last_usage whenever a chunk carries it.
                # After the loop, last_usage will hold the final totals.
                if chunk.usage_metadata:
                    last_usage = chunk.usage_metadata

            # Stream is fully consumed — write to cache
            self._cache.set(system, user, self._model, full_text)

            # Populate the StreamResult's usage fields (deferred population)
            if last_usage is not None:
                result.input_tokens = last_usage.prompt_token_count or 0
                result.output_tokens = last_usage.candidates_token_count or 0
            else:
                # No chunk carried usage data — unusual but non-fatal
                logger.warning("Gemini stream [%s] returned no usage metadata", self._model)

            logger.info(
                "Gemini stream [%s] input=%d output=%d",
                self._model,
                result.input_tokens,
                result.output_tokens,
            )

        result.tokens = _gen()
        return result
