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
                  "options": {"num_predict": N, "num_ctx": C}, "keep_alive": "30m"}
  Streaming:     same but "stream": true; response is ndjson lines.

Each streaming line: {"response": "<token>", "done": false}
Final line:          {"response": "", "done": true,
                      "prompt_eval_count": N, "eval_count": M}

Ollama is typically available at http://localhost:11434 (native) or
http://ollama:11434 (inside Docker Compose, where the service name resolves).

CONTEXT WINDOW, TIMEOUT, KEEP-ALIVE (ADR-039)
---------------------------------------------
- ``num_ctx`` is sent on EVERY call. Ollama's default window is 4096 tokens;
  the production prompt (v9 + few-shot + grounding) is ~7.6k, and Ollama does
  not fail on overflow — it silently drops the start of the prompt (measured:
  2,050 of 7,585 tokens reached the model, which then wrote invalid SPARQL).
- The timeout is long because a CPU reads the whole prompt before the first
  token is sent (98 s for a 1.5B model, 192 s for 3B, on the dev laptop).
- ``keep_alive`` keeps the model loaded between questions. The system prompt
  is identical for every question (ADR-026), so a loaded model reuses it from
  its prefix cache: the second question read the prompt in 3.6 s, not 86 s.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Iterator

import httpx

from app.llm.base import LLMResponse, StreamResult
from app.llm.cache import DiskCache

logger = logging.getLogger(__name__)


class OllamaProvider:
    """Talks to a local Ollama instance and wraps every call with a disk cache.

    Constructed once per request by factory.get_provider("ollama", model).
    The model name must match an installed Ollama model (e.g. "qwen2.5:3b-instruct").
    """

    def __init__(
        self,
        model: str,
        base_url: str,
        cache: DiskCache,
        *,
        num_ctx: int = 12288,
        timeout: float = 600.0,
        keep_alive: str = "30m",
    ) -> None:
        """
        Parameters
        ----------
        model : str
            Ollama model tag, e.g. "qwen2.5:3b-instruct".
        base_url : str
            Ollama server base URL, e.g. "http://localhost:11434".
        cache : DiskCache
            Shared disk cache — same as used by Claude/Gemini providers.
        num_ctx : int
            Context window in tokens (settings.ollama_num_ctx). Must fit the
            whole prompt plus the answer, or Ollama truncates the prompt.
        timeout : float
            Seconds to wait for Ollama (settings.ollama_timeout).
        keep_alive : str
            How long Ollama keeps the model loaded afterwards
            (settings.ollama_keep_alive), e.g. "30m".
        """
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._cache = cache
        self._num_ctx = num_ctx
        self._timeout = timeout
        self._keep_alive = keep_alive

    def _payload(self, system: str, user: str, max_tokens: int, *, stream: bool) -> dict[str, Any]:
        """Build the /api/generate request body shared by generate() and stream()."""
        return {
            "model": self._model,
            "system": system,
            "prompt": user,
            "stream": stream,
            "options": {"num_predict": max_tokens, "num_ctx": self._num_ctx},
            "keep_alive": self._keep_alive,
        }

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
            json=self._payload(system, user, max_tokens, stream=False),
            timeout=self._timeout,
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
                json=self._payload(system, user, max_tokens, stream=True),
                timeout=self._timeout,
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
