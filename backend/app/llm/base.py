"""LLMProvider protocol and response dataclasses shared by all provider implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterator, Protocol, runtime_checkable


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int


@dataclass
class StreamResult:
    """Wraps a streaming token iterator with usage metadata.

    input_tokens and output_tokens are 0 until the tokens iterator is fully
    exhausted — the provider's generator closure populates them at that point.
    """

    tokens: Iterator[str]
    input_tokens: int = field(default=0)
    output_tokens: int = field(default=0)


@runtime_checkable
class LLMProvider(Protocol):
    def generate(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse: ...

    def stream(self, system: str, user: str, *, max_tokens: int = 1024) -> StreamResult: ...
