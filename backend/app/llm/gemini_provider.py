"""Google Gemini implementation of LLMProvider.

Only this file may import google.genai — all other modules must go through the
LLMProvider protocol to keep the provider abstraction honest.
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
    """Google Gemini implementation. Wraps every call with a disk cache."""

    def __init__(self, model: str, api_key: str, cache: DiskCache) -> None:
        self._model = model
        self._client = genai.Client(api_key=api_key)
        self._cache = cache

    def generate(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse:
        """Generate a response. Returns cached result if available."""
        cached = self._cache.get(system, user, self._model)
        if cached is not None:
            return LLMResponse(text=cached, input_tokens=0, output_tokens=0)

        response = self._client.models.generate_content(
            model=self._model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=max_tokens,
            ),
        )
        text = response.text
        if text is None:
            raise RuntimeError("Gemini returned no text content")
        usage = response.usage_metadata
        if usage is None:
            raise RuntimeError("Gemini returned no usage metadata")
        prompt_tokens = usage.prompt_token_count or 0
        candidate_tokens = usage.candidates_token_count or 0
        self._cache.set(system, user, self._model, text)

        logger.info(
            "Gemini [%s] input=%d output=%d",
            self._model,
            prompt_tokens,
            candidate_tokens,
        )
        return LLMResponse(
            text=text,
            input_tokens=prompt_tokens,
            output_tokens=candidate_tokens,
        )

    def stream(self, system: str, user: str, *, max_tokens: int = 1024) -> StreamResult:
        """Return a StreamResult whose tokens iterator yields raw text tokens.

        input_tokens and output_tokens on the returned StreamResult are populated
        after the tokens iterator is fully exhausted.
        """
        result = StreamResult(tokens=iter([]))

        def _gen() -> Iterator[str]:
            cached = self._cache.get(system, user, self._model)
            if cached is not None:
                yield cached
                return

            full_text = ""
            last_usage = None
            for chunk in self._client.models.generate_content_stream(
                model=self._model,
                contents=user,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=max_tokens,
                ),
            ):
                if chunk.text:
                    full_text += chunk.text
                    yield chunk.text
                if chunk.usage_metadata:
                    last_usage = chunk.usage_metadata

            self._cache.set(system, user, self._model, full_text)
            if last_usage is not None:
                result.input_tokens = last_usage.prompt_token_count or 0
                result.output_tokens = last_usage.candidates_token_count or 0
            else:
                logger.warning("Gemini stream [%s] returned no usage metadata", self._model)
            logger.info(
                "Gemini stream [%s] input=%d output=%d",
                self._model,
                result.input_tokens,
                result.output_tokens,
            )

        result.tokens = _gen()
        return result
