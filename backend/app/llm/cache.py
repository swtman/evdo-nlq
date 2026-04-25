"""Disk cache for LLM responses, keyed on sha256(system + user + model).

Prevents re-calling the API for identical prompts during development.
Cache directory is gitignored. Disable with LLM_CACHE_DISABLED=1.
"""
from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


class DiskCache:
    """SHA-256 keyed disk cache for LLM responses."""

    def __init__(self, cache_dir: str, disabled: bool = False) -> None:
        self._dir = Path(cache_dir)
        self._disabled = disabled
        if not disabled:
            self._dir.mkdir(parents=True, exist_ok=True)

    def _key(self, system: str, user: str, model: str) -> str:
        payload = json.dumps(
            {"system": system, "user": user, "model": model}, ensure_ascii=False
        )
        return hashlib.sha256(payload.encode()).hexdigest()

    def get(self, system: str, user: str, model: str) -> str | None:
        """Return cached response text, or None on miss."""
        if self._disabled:
            return None
        path = self._dir / self._key(system, user, model)
        if path.exists():
            logger.debug("Cache hit: %s", path.name[:12])
            return path.read_text(encoding="utf-8")
        return None

    def set(self, system: str, user: str, model: str, value: str) -> None:
        """Write response text to cache."""
        if self._disabled:
            return
        path = self._dir / self._key(system, user, model)
        path.write_text(value, encoding="utf-8")
        logger.debug("Cache write: %s", path.name[:12])
