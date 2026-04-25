# ADR-002: Pluggable LLM provider abstraction

- **Status:** Accepted
- **Date:** 2026-04-22
- **Deciders:** @swtman

## Context

One of the thesis's potential contributions (per the project brief) is "comparison of the performance of various LLMs." We also want a cost-sensitive development workflow (fake provider for tests, cheap model by default). Both require that swapping models does not ripple through the codebase.

## Options considered

### Option A — Import the Anthropic SDK directly throughout the code
- Pros: Simplest. Fewest layers of indirection.
- Cons: Later swap to OpenAI or Ollama requires touching every call site. Hard to test without a live key. Kills the comparison experiment.

### Option B — Thin `LLMProvider` protocol + one implementation per provider
- Pros: Adding a provider = one new file. Tests and UI use a `FakeProvider`. Comparison experiments iterate over providers in a loop.
- Cons: Tiny amount of extra code upfront. Some providers have features (tool use, structured output) that don't map to a common interface.

### Option C — LangChain (or similar framework)
- Pros: Pre-built abstractions, many providers supported.
- Cons: Heavy dependency, high churn, abstractions hide what's happening — bad for a thesis where we want to explain every step. Introduces concepts outside the thesis scope.

## Decision

We chose **Option B — a minimal in-house `LLMProvider` protocol**.

```python
class LLMProvider(Protocol):
    name: str
    model: str
    def generate(self, system: str, user: str, *, max_tokens: int = 1024) -> LLMResponse: ...

@dataclass
class LLMResponse:
    text: str
    input_tokens: int | None
    output_tokens: int | None
    raw: dict
```

Implementations: `ClaudeProvider`, `OpenAIProvider` (later), `OllamaProvider` (later), `FakeProvider` (always).

## Consequences

- A one-line change in `.env` swaps providers — exactly what the thesis's comparison chapter needs.
- Tests never hit a real API.
- The frontend development loop stays cheap: run backend with `LLM_PROVIDER=fake`.
- We deliberately do not use LangChain — simpler code, fewer moving parts, easier to explain in the thesis.
- We accept that provider-specific features (Claude's tool use, OpenAI's function calling) are out of scope for v1.

## Follow-ups

- [ ] Implement `FakeProvider` first, then `ClaudeProvider`.
- [ ] Add a provider comparison script under `scripts/eval.py` (Phase 3).
