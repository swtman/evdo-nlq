"""
Grounding package — pre-LLM entity resolution and Greek morphology for evdograph-nlq.

The grounding module runs before the LLM call and injects resolved hints into the
system prompt so the model uses exact canonical labels and word stems rather than
whatever surface form the user typed.

Public API:
    build_grounding_hints  — orchestrates tokenization, entity resolution, and
                             stemming; returns a formatted markdown block (or "")
                             ready for injection into the system prompt.
"""

from app.grounding.hints import build_grounding_hints

__all__ = ["build_grounding_hints"]
