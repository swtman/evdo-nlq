"""
Ollama implementation of LLMProvider.

BOUNDARY RULE
-------------
Only this file may use httpx to call the Ollama HTTP API.
All other modules interact with Ollama through the LLMProvider protocol.

OLLAMA API USED
---------------
POST /api/generate
  Non-streaming: {"model": ..., "system": ..., "prompt": ..., "stream": false,
                  "options": {"num_predict": N}}
  Streaming:     same but "stream": true; response is ndjson lines.

Each streaming line: {"response": "<token>", "done": false}
Final line:          {"response": "", "done": true,
                      "prompt_eval_count": N, "eval_count": M}

Ollama is typically available at http://localhost:11434 (native) or
http://ollama:11434 (inside Docker Compose, where the service name resolves).
"""

from __future__ import annotations

import json
import logging
from typing import Iterator

import httpx

from app.llm.base import LLMResponse, StreamResult
from app.llm.cache import DiskCache

logger = logging.getLogger(__name__)


class OllamaProvider:
    """Talks to a local Ollama instance and wraps every call with a disk cache.

    Constructed once per request by factory.get_provider("ollama", model).
    The model name must match an installed Ollama model (e.g. "qwen2.5:3b-instruct").
    """

    def __init__(self, model: str, base_url: str, cache: DiskCache) -> None:
        """
        Parameters
        ----------
        model : str
            Ollama model tag, e.g. "qwen2.5:3b-instruct".
        base_url : str
            Ollama server base URL, e.g. "http://localhost:11434".
        cache : DiskCache
            Shared disk cache — same as used by Claude/Gemini providers.
        """
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._cache = cache

    # ------------------------------------------------------------------
    # generate() — non-streaming path
    # ------------------------------------------------------------------

    def generate(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse:
        """Ask Ollama for a complete answer and wait for it to finish."""
        cached = self._cache.get(system, user, self._model)
        if cached is not None:
            return LLMResponse(text=cached, input_tokens=0, output_tokens=0)

        response = httpx.post(
            f"{self._base_url}/api/generate",
            json={
                "model": self._model,
                "system": system,
                "prompt": user,
                "stream": False,
                "options": {"num_predict": max_tokens},
            },
            timeout=120.0,
        )
        response.raise_for_status()
        data = response.json()
        text = data["response"]

        self._cache.set(system, user, self._model, text)

        input_tokens = data.get("prompt_eval_count", 0)
        output_tokens = data.get("eval_count", 0)
        logger.info(
            "Ollama [%s] input=%d output=%d",
            self._model,
            input_tokens,
            output_tokens,
        )
        return LLMResponse(text=text, input_tokens=input_tokens, output_tokens=output_tokens)

    # ------------------------------------------------------------------
    # stream() — streaming path (deferred-population pattern)
    # ------------------------------------------------------------------

    def stream(self, system: str, user: str, *, max_tokens: int = 1024) -> StreamResult:
        """Ask Ollama for an answer delivered token-by-token.

        Uses the same deferred-population closure pattern as ClaudeProvider:
        StreamResult is returned immediately; usage fields are set after the
        caller exhausts the `tokens` iterator.
        """
        result = StreamResult(tokens=iter([]))

        def _gen() -> Iterator[str]:
            cached = self._cache.get(system, user, self._model)
            if cached is not None:
                yield cached
                return

            full_text = ""
            with httpx.stream(
                "POST",
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "system": system,
                    "prompt": user,
                    "stream": True,
                    "options": {"num_predict": max_tokens},
                },
                timeout=120.0,
            ) as response:
                for line in response.iter_lines():
                    if not line:
                        continue
                    chunk = json.loads(line)
                    token = chunk.get("response", "")
                    if token:
                        full_text += token
                        yield token
                    if chunk.get("done"):
                        self._cache.set(system, user, self._model, full_text)
                        result.input_tokens = chunk.get("prompt_eval_count", 0)
                        result.output_tokens = chunk.get("eval_count", 0)
                        logger.info(
                            "Ollama stream [%s] input=%d output=%d",
                            self._model,
                            result.input_tokens,
                            result.output_tokens,
                        )

        result.tokens = _gen()
        return result
