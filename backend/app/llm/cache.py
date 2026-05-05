"""
Disk cache for LLM responses.

WHY THIS EXISTS
---------------
Every call to a real LLM (Claude, Gemini) costs money and takes time. During
development you often send the *exact same question* over and over while
tweaking unrelated parts of the code. Without a cache, you'd pay for the same
API call hundreds of times.

This cache stores each LLM response as a plain text file on disk. The next
time the exact same inputs arrive, it returns the saved file instead of
calling the API again. Free and instant.

HOW THE CACHE KEY WORKS
------------------------
The cache must distinguish between calls that look similar but differ in some
way — different question, different model, different system prompt, etc. It
does this by hashing all three inputs together into a single 64-character
fingerprint (a SHA-256 hash). Each cached response is saved as a file whose
name is that fingerprint.

WHAT IS A HASH?
---------------
A hash function takes any input (text, numbers, files…) and produces a fixed-
length string that looks like random characters, e.g.:

    "What is Python?" + system prompt + "claude-haiku-4-5"
    → "a3f92bc1d8e047..."  (64 hex characters)

Two different inputs will (in practice, always) produce two different hashes.
The same inputs always produce the same hash. This makes hashes perfect as
unique file names.

HOW TO DISABLE THE CACHE
-------------------------
Set `LLM_CACHE_DISABLED=1` in your `.env` file (or in your shell). Both
`get()` and `set()` become no-ops, so every request hits the real API.
Useful when you change a prompt and want to see fresh model output.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

# `logging.getLogger(__name__)` creates a logger whose name matches this
# module's import path (e.g. "app.llm.cache"). Log messages from this module
# will be prefixed with that name, making it easy to find them in the output.
logger = logging.getLogger(__name__)


class DiskCache:
    """A simple file-based cache for LLM responses.

    Each unique combination of (system prompt, user message, model name) maps
    to exactly one file on disk. If that file exists, the cached text is
    returned without calling the API. If it doesn't exist, `get()` returns
    None and the caller is expected to call the API and then call `set()`.

    Usage pattern (used inside every real provider)
    -----------------------------------------------
        cached = cache.get(system, user, model)
        if cached is not None:
            return cached          # free — no API call

        response = call_the_api(system, user, model)
        cache.set(system, user, model, response.text)
        return response
    """

    def __init__(self, cache_dir: str, disabled: bool = False) -> None:
        """Set up the cache directory.

        Parameters
        ----------
        cache_dir : str
            Path to the folder where cached files will be stored.
            Typically `.llm_cache/` inside the `backend/` folder (gitignored).
        disabled : bool
            When True, all cache operations become no-ops. The folder is not
            even created. Controlled by the `LLM_CACHE_DISABLED` env var.
        """
        # `Path` is Python's object-oriented way of working with file paths.
        # It handles differences between operating systems (/ vs \) for you.
        self._dir = Path(cache_dir)
        self._disabled = disabled

        if not disabled:
            # `mkdir(parents=True, exist_ok=True)` creates the folder and any
            # missing parent folders. Does nothing if the folder already exists.
            self._dir.mkdir(parents=True, exist_ok=True)

    def _key(self, system: str, user: str, model: str) -> str:
        """Compute a unique 64-character fingerprint for the given inputs.

        Combines all three values into a JSON string first (to avoid edge cases
        where concatenating strings could produce the same result from
        different inputs), then hashes that string with SHA-256.

        The result is a 64-character hex string used as the cache file name.
        This method is private (leading underscore) — only used internally.
        """
        # `json.dumps` turns the dict into a stable, predictable string.
        # `ensure_ascii=False` keeps Greek characters as-is rather than
        # escaping them to \uXXXX sequences.
        payload = json.dumps({"system": system, "user": user, "model": model}, ensure_ascii=False)

        # `.encode()` converts the string to bytes (SHA-256 works on bytes).
        # `.hexdigest()` returns the hash as a readable hex string.
        return hashlib.sha256(payload.encode()).hexdigest()

    def get(self, system: str, user: str, model: str) -> str | None:
        """Look up a cached response.

        Returns the cached text if a matching file exists, or None if there
        is no cache entry for these inputs (a "cache miss").

        The caller should treat None as a signal to call the real API.

        Parameters
        ----------
        system : str
            The system prompt that was sent to the LLM.
        user : str
            The user's natural-language question.
        model : str
            The model name (e.g. "claude-haiku-4-5"). Different models can
            return different answers for the same question, so the model is
            part of the key.
        """
        if self._disabled:
            return None  # cache is turned off — always a miss

        path = self._dir / self._key(system, user, model)

        if path.exists():
            # Log only the first 12 characters of the hash — enough to
            # identify the file in logs without flooding the output.
            logger.debug("Cache hit: %s", path.name[:12])
            return path.read_text(encoding="utf-8")

        return None  # file not found → cache miss

    def set(self, system: str, user: str, model: str, value: str) -> None:
        """Save a response to the cache.

        Writes `value` (the LLM's response text) to a file whose name is the
        hash of the inputs. Future calls to `get()` with the same inputs will
        find this file and return it instantly.

        Parameters
        ----------
        system : str
            The system prompt used for this call.
        user : str
            The user's natural-language question.
        model : str
            The model name used for this call.
        value : str
            The full text response from the LLM to cache.
        """
        if self._disabled:
            return  # cache is turned off — silently do nothing

        path = self._dir / self._key(system, user, model)
        path.write_text(value, encoding="utf-8")
        logger.debug("Cache write: %s", path.name[:12])
