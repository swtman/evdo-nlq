"""Google Gemini implementation of LLMProvider.

Only this file may import google.genai — all other modules must go through the
LLMProvider protocol to keep the provider abstraction honest.
"""

from __future__ import annotations

import logging
from typing import Iterator

import google.genai as genai
from google.genai import types

from app.llm.base import LLMResponse
from app.llm.cache import DiskCache

logger = logging.getLogger(__name__)


class GeminiProvider:
    """Google Gemini implementation. Wraps every call with a disk cache."""

    def __init__(self, model: str, api_key: str, cache: DiskCache) -> None:
        self._model = model
        self._client = genai.Client(api_key=api_key)
        self._cache = cache
        # Set after stream() completes — read by the streaming endpoint for the done event.
        self.last_input_tokens: int = 0
        self.last_output_tokens: int = 0

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
        usage = response.usage_metadata
        self._cache.set(system, user, self._model, text)

        logger.info(
            "Gemini [%s] input=%d output=%d",
            self._model,
            usage.prompt_token_count,
            usage.candidates_token_count,
        )
        return LLMResponse(
            text=text,
            input_tokens=usage.prompt_token_count,
            output_tokens=usage.candidates_token_count,
        )

    def stream(self, system: str, user: str, *, max_tokens: int = 1024) -> Iterator[str]:
        """Stub — implemented in Task 3."""
        raise NotImplementedError
