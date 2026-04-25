"""Claude (Anthropic) implementation of LLMProvider.

Only this file may import anthropic — all other modules must go through the
LLMProvider protocol to keep the provider abstraction honest.
"""

from __future__ import annotations

import logging
from typing import Iterator

import anthropic

from app.llm.base import LLMResponse
from app.llm.cache import DiskCache

logger = logging.getLogger(__name__)


class ClaudeProvider:
    """Anthropic Claude implementation. Wraps every call with a disk cache."""

    def __init__(self, model: str, api_key: str, cache: DiskCache) -> None:
        self._model = model
        self._client = anthropic.Anthropic(api_key=api_key)
        self._cache = cache
        # Set after stream() completes — read by the streaming endpoint for the done event.
        self.last_input_tokens: int = 0
        self.last_output_tokens: int = 0

    def generate(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse:
        """Generate a response. Returns cached result if available."""
        cached = self._cache.get(system, user, self._model)
        if cached is not None:
            return LLMResponse(text=cached, input_tokens=0, output_tokens=0)

        message = self._client.messages.create(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = message.content[0].text
        self._cache.set(system, user, self._model, text)

        logger.info(
            "Claude [%s] input=%d output=%d",
            self._model,
            message.usage.input_tokens,
            message.usage.output_tokens,
        )
        return LLMResponse(
            text=text,
            input_tokens=message.usage.input_tokens,
            output_tokens=message.usage.output_tokens,
        )

    def stream(self, system: str, user: str, *, max_tokens: int = 1024) -> Iterator[str]:
        """Yield raw text tokens from the Claude streaming API.

        After the generator is exhausted, last_input_tokens and last_output_tokens
        are set so callers can include them in the SSE 'done' event.

        TODO: future — run in a thread pool to avoid blocking the async event loop.
        """
        cached = self._cache.get(system, user, self._model)
        if cached is not None:
            yield cached
            return

        full_text = ""
        with self._client.messages.stream(
            model=self._model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        ) as stream:
            for token in stream.text_stream:
                full_text += token
                yield token

        self._cache.set(system, user, self._model, full_text)
        usage = stream.get_final_message().usage
        self.last_input_tokens = usage.input_tokens
        self.last_output_tokens = usage.output_tokens
        logger.info(
            "Claude stream [%s] input=%d output=%d",
            self._model,
            self.last_input_tokens,
            self.last_output_tokens,
        )
