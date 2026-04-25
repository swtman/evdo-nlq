"""LLMProvider protocol and response dataclass shared by all provider implementations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, Protocol, runtime_checkable


@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int


@runtime_checkable
class LLMProvider(Protocol):
    def generate(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse: ...

    def stream(self, system: str, user: str, *, max_tokens: int = 1024) -> Iterator[str]: ...
