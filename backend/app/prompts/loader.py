"""
Loads and fills versioned prompt templates from the top-level prompts/ directory.

WHY PROMPTS LIVE IN FILES, NOT IN CODE
---------------------------------------
Prompt text changes frequently during development (tweaking wording, adding
examples, adjusting instructions). If prompts were inlined as Python strings,
every change would show up as a code diff, mixed together with real logic
changes. Keeping them in Markdown files means:
  - Prompt history is readable in git without sifting through code.
  - You can edit prompts without touching Python.
  - The `name-v{N}.md` naming convention makes versions explicit and
    lets you compare v1 vs v2 side-by-side.

HOW A PROMPT FILE IS STRUCTURED
---------------------------------
Each `.md` file can have three sections:

    ---
    (YAML frontmatter — metadata like author, date, notes)
    ---

    # System
    (The actual system prompt text injected into every LLM call.
     This is the part the loader extracts.)

    # Notes
    (Developer notes, not sent to the LLM.)

`load()` strips the frontmatter, extracts only the `# System` section, and
discards everything after it.

HOW THE MODULE-LEVEL CACHE WORKS
---------------------------------
`_cache` is a dictionary (a dict) defined at module level, outside any
function. The first time `load("nl-to-sparql", 1)` is called, it reads and
parses the file, then stores the result in `_cache["nl-to-sparql-v1"]`. Every
subsequent call returns that stored value directly — no disk read, no regex.

This is the same idea as in `ontology/loader.py`, but using a dict instead of
a single variable so multiple different prompts can be cached at once.

WHAT IS A REGULAR EXPRESSION (regex)?
--------------------------------------
A regular expression is a pattern that describes text. Python's `re` module
uses them to search, extract, and replace text. Two regexes are used here:

  1. To strip YAML frontmatter:  r"\A---\n.*?\n---\n*"
     \A  = start of the whole string
     --- = literal three dashes
     .*? = any characters (non-greedy — stops at the first match)
     This removes the opening --- ... --- block.

  2. To extract the # System section:  r"^# System\n(.*?)(?=^# |\Z)"
     ^# System  = a line starting with "# System"
     (.*?)      = capture everything after it (non-greedy)
     (?=^# |\Z) = stop when the next top-level heading or end of file is found
     re.MULTILINE makes ^ match the start of any line, not just the whole string.
     re.DOTALL   makes . also match newlines (so .*? spans multiple lines).
"""

from __future__ import annotations

import re
from pathlib import Path

# Absolute path to the prompts/ folder, resolved the same way as in
# ontology/loader.py — four .parent steps walk up to the repo root.
_PROMPTS_DIR = Path(__file__).parent.parent.parent.parent / "prompts"

# Module-level cache: maps "name-vN" keys to their extracted prompt text.
# A dict is used (instead of a single variable) so multiple prompts can be
# cached simultaneously without interfering with each other.
# `dict[str, str]` means: keys are strings, values are strings.
_cache: dict[str, str] = {}


def load(name: str, version: int) -> str:
    """Return the '# System' section of a versioned prompt template.

    Reads the file `prompts/{name}-v{version}.md`, strips YAML frontmatter,
    extracts only the text under the `# System` heading, caches the result,
    and returns it as a plain string ready to be passed to an LLM.

    Parameters
    ----------
    name : str
        The prompt's base name, e.g. "nl-to-sparql" or "nl-to-sparql-retry".
        This becomes part of the filename: `nl-to-sparql-v1.md`.
    version : int
        The version number. Allows multiple versions to coexist in prompts/.

    Returns
    -------
    str
        The text of the `# System` section, with leading/trailing whitespace
        stripped. This is the string injected into every LLM system prompt.

    Raises
    ------
    FileNotFoundError
        If the expected .md file does not exist in prompts/.
    ValueError
        If the file exists but has no `# System` section.
    """
    # Build the cache key, e.g. "nl-to-sparql-v1"
    key = f"{name}-v{version}"

    # Return immediately if already cached
    if key in _cache:
        return _cache[key]

    # First call for this key — read from disk
    path = _PROMPTS_DIR / f"{name}-v{version}.md"
    if not path.exists():
        raise FileNotFoundError(f"Prompt not found: {path}")

    raw = path.read_text(encoding="utf-8")

    # Step 1 — strip YAML frontmatter if present.
    # \A matches the very start of the string (not just the start of a line).
    # .*? is non-greedy: it matches as little as possible, stopping at the
    # first closing ---.
    # re.DOTALL makes . match newlines too, so .*? spans multiple lines.
    raw = re.sub(r"\A---\n.*?\n---\n*", "", raw, flags=re.DOTALL)

    # Step 2 — extract the # System section.
    # re.MULTILINE makes ^ match the start of any line (not just the string).
    # re.DOTALL makes . match newlines so (.*?) can span multiple lines.
    # (?=^# |\Z) is a "lookahead": stop before the next top-level heading
    # or the end of the string — but don't consume those characters.
    m = re.search(r"^# System\n(.*?)(?=^# |\Z)", raw, re.MULTILINE | re.DOTALL)
    if not m:
        raise ValueError(f"No '# System' section found in {path.name}")

    # m.group(1) is the text captured by the first set of parentheses (.*?)
    result = m.group(1).strip()

    # Store in cache for future calls
    _cache[key] = result
    return result


def fill(template: str, **kwargs: str) -> str:
    """Substitute {placeholder} slots in a prompt template string.

    Each prompt template's `# System` section may contain placeholders —
    `{word}` patterns that get replaced with real values before the text
    is sent to the LLM. This function performs those substitutions safely.

    WHICH PLACEHOLDERS EXIST AND WHERE
    ------------------------------------
    This depends on which template was loaded. The two templates in use:

    `nl-to-sparql-v1.md` (main prompt, first attempt):
        System section contains only: {ontology_summary}
        The user's question is NOT a placeholder here — it is passed
        directly as the `user` argument to the LLM (provider.stream /
        provider.generate). The `# User (template)` section in the .md
        file is just documentation to show the message shape; load() never
        extracts it, so {question} never appears in the filled string.

        Typical call:
            fill(template, ontology_summary=load_summary())

    `nl-to-sparql-retry-v1.md` (retry prompt, after SPARQL validation fails):
        System section contains: {ontology_summary}, {failed_sparql},
        {error}, and {question}.
        Here the question IS substituted into the system prompt because
        the retry prompt bundles everything — original question, failed
        query, and error message — into a single system message.

        Typical call:
            fill(template,
                 ontology_summary=load_summary(),
                 question="Ποια βιβλία υπάρχουν;",
                 failed_sparql="SELECT ...",
                 error="Unknown property evdx:foo")

    WHY NOT USE Python's built-in str.format()?
    --------------------------------------------
    SPARQL queries use curly braces heavily, e.g. `WHERE { ?book a evdx:Book }`.
    If we used `str.format()`, Python would try to interpret those SPARQL braces
    as placeholders too and crash with a KeyError or produce garbled output.

    Instead, this function only replaces `{word}` patterns where `word` is a
    simple identifier (letters, digits, underscores) AND is a key in `kwargs`.
    Any other curly brace — like `{ ?book a evdx:Book }` — is left untouched.

    Parameters
    ----------
    template : str
        The prompt text (the `# System` section) containing `{placeholder}`
        slots.
    **kwargs : str
        The values to substitute. Only slots whose names match a key in
        kwargs are replaced — unrecognised slots are left as-is.

    Returns
    -------
    str
        The template with all known placeholders replaced. Unknown
        placeholders (not in kwargs) are left as-is.

    Example
    -------
        fill("Hello {name}! WHERE { ?x a {type} }", name="Claude")
        → "Hello Claude! WHERE { ?x a {type} }"
        # {name} was replaced; {type} was left alone (not in kwargs);
        # the SPARQL braces around ?x were untouched (contain spaces).
    """
    return re.sub(
        r"\{(\w+)\}",          # match {word} where word is letters/digits/underscore
        lambda m: kwargs.get(  # for each match, look up m.group(1) in kwargs
            m.group(1),        # the captured word, e.g. "ontology"
            m.group(0),        # default: return the original {word} unchanged
        ),
        template,
    )
