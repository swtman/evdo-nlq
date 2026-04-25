"""Loads versioned prompt templates from the top-level prompts/ directory."""
from __future__ import annotations

import re
from pathlib import Path

# prompts/ lives four levels up from this file (backend/app/prompts/loader.py → repo root)
_PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts"


def load(name: str, version: int) -> str:
    """Return the '# System' section of a versioned prompt template.

    Strips YAML frontmatter and discards all sections after '# System'.
    """
    path = _PROMPTS_DIR / f"{name}-v{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")

    raw = path.read_text(encoding="utf-8")

    # Strip YAML frontmatter (--- ... ---)
    raw = re.sub(r"\A---\n.*?\n---\n*", "", raw, flags=re.DOTALL)

    # Extract the '# System' section up to the next top-level heading or EOF
    m = re.search(r"^# System\n(.*?)(?=^# |\Z)", raw, re.MULTILINE | re.DOTALL)
    if not m:
        raise ValueError(f"No '# System' section found in {path.name}")

    return m.group(1).strip()


def fill(template: str, **kwargs: str) -> str:
    """Substitute {slot} placeholders in a prompt template.

    Only replaces {word} patterns where 'word' is a key in kwargs.
    Curly braces containing spaces or special chars (SPARQL patterns) are untouched.
    """
    return re.sub(
        r"\{(\w+)\}",
        lambda m: kwargs.get(m.group(1), m.group(0)),
        template,
    )
