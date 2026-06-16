"""Grounding orchestrator — builds hint blocks for LLM system prompts.

WHAT THIS MODULE DOES
---------------------
``build_grounding_hints(question)`` is the single public entry point for the
grounding module.  Given a raw user question (Greek or English), it:

  1. Tokenizes the question into individual word tokens.
  2. Resolves entity mentions (single tokens AND 2/3-token windows) via
     ``linker.resolve_mention``.
  3. Stems remaining topic words via ``stem.greek_stem``.
  4. Formats the results into a markdown block ready for injection into the
     system prompt that precedes the LLM SPARQL-generation call.

WHY INJECT HINTS INTO THE SYSTEM PROMPT?
-----------------------------------------
The LLM must produce SPARQL that uses exact ``evdx:name`` strings (e.g.
"ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ") because EvdoGraph does not support
free-text full-text search — all filters are FILTER(CONTAINS(...)) or exact
VALUES.  If the model guesses a name it tends to hallucinate partial or
accented variants that return zero results.  Grounding resolves the user's
intent (e.g. "ΑΠΘ") to the canonical KG label before the model runs, so the
hint block can say "use this exact string".

Topic stems solve the inflection problem: "αλγοριθμων" (genitive plural) does
not appear verbatim in any book title, but the stem "αλγορ" does appear as a
CONTAINS substring of the normalized title "ΑΛΓΟΡΙΘΜΟΙ ΚΑΙ ΔΟΜΕΣ ΔΕΔΟΜΕΝΩΝ".

DEDUPLICATION ACROSS WINDOWS
------------------------------
The same canonical label may fire for multiple overlapping windows (e.g. a
bigram and a trigram that both resolve to the same entity).  We keep the
highest-priority match (acronym > exact > fuzzy) per canonical label, matching
the contract of ``linker._deduplicate``.
"""

from __future__ import annotations

import re

from app.grounding.linker import ResolvedEntity, resolve_mention
from app.grounding.normalize import normalize_greek
from app.grounding.stem import greek_stem

# ---------------------------------------------------------------------------
# Greek stopwords (normalized form — accent-free, lowercase, ς→σ)
# ---------------------------------------------------------------------------

_GREEK_STOPWORDS: frozenset[str] = frozenset({
    # Articles
    "ο", "η", "το", "οι", "τα", "τον", "την", "τησ", "του", "των", "τοισ", "ταισ",
    # Prepositions
    "σε", "στο", "στη", "στον", "στην", "στα", "απο", "για", "στισ", "απ",
    "μεσ", "με", "κατα", "προσ", "ωσ", "περι",
    # Conjunctions
    "και", "η", "αλλα", "ομωσ", "ενω", "οτι", "που", "πωσ",
    # Pronouns
    "εγω", "εσυ", "αυτοσ", "αυτη", "αυτο", "αυτοι", "αυτεσ", "αυτα",
    "ποιοσ", "ποια", "ποιο",
    # Common verbs
    "ειναι", "εχει", "εχουν", "ειχε", "εχω", "θελω",
    # Question words
    "ποια", "ποιοσ", "ποιεσ", "ποιων", "ποσα", "ποτε", "που", "πωσ", "γιατι",
    # Common domain nouns (too generic to be useful stems)
    "βιβλια", "βιβλιο", "μαθημα", "μαθηματα", "κουρσα", "κορσα",
    "τμημα", "πανεπιστημιο", "τεχνολογικο", "ιδρυμα",
    "σχολη", "σχολεσ", "σχολων", "ετοσ", "χρονια",
    # Numbers as words
    "ενα", "δυο", "τρια", "τεσσερα",
})

# Priority for deduplicating entity matches across window sizes.
# Lower number = higher semantic confidence.
_STAGE_PRIORITY: dict[str, int] = {"acronym": 0, "exact": 1, "fuzzy": 2}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _tokenize(question: str) -> list[str]:
    """Extract word-only tokens from a Greek/English question string.

    Uses a Unicode-aware regex to pull out sequences of non-whitespace,
    non-punctuation, non-digit characters.  Then filters:
      - Tokens shorter than 3 characters (too short for meaningful matching).
      - Tokens whose normalized form is in ``_GREEK_STOPWORDS``.

    Args:
        question: Raw user question, any Unicode text.

    Returns:
        List of raw token strings that survive the filter (original casing
        preserved so that acronym detection like "ΑΠΘ" works at full uppercase).
    """
    # re.findall with a Unicode word-char pattern: letters only (no digits, no punct).
    raw_tokens: list[str] = re.findall(r"[^\s\W\d]+", question, flags=re.UNICODE)

    result: list[str] = []
    for tok in raw_tokens:
        if len(tok) < 3:  # too short to be meaningful
            continue
        if normalize_greek(tok) in _GREEK_STOPWORDS:
            continue
        result.append(tok)
    return result


def _sliding_windows(tokens: list[str], size: int) -> list[str]:
    """Generate joined sliding windows of ``size`` tokens from ``tokens``.

    Args:
        tokens: List of raw token strings.
        size: Window size (2 for bigrams, 3 for trigrams).

    Returns:
        List of space-joined window strings.  Empty if len(tokens) < size.
    """
    return [" ".join(tokens[i : i + size]) for i in range(len(tokens) - size + 1)]


def _resolve_all_windows(tokens: list[str]) -> dict[str, ResolvedEntity]:
    """Resolve entity mentions from all unigram, bigram, and trigram windows.

    Deduplicates by ``canonical_label``, keeping the highest-priority match
    method (acronym > exact > fuzzy) per label.

    Args:
        tokens: Filtered token list from ``_tokenize``.

    Returns:
        Dict mapping ``canonical_label → ResolvedEntity`` for every distinct
        entity found.  Empty dict if nothing resolves.
    """
    # Collect all candidates across all window sizes.
    all_candidates: list[ResolvedEntity] = []
    for size in (1, 2, 3):
        for window in _sliding_windows(tokens, size):
            all_candidates.extend(resolve_mention(window))

    # Deduplicate: for the same canonical label, keep the highest-priority entry.
    best: dict[str, ResolvedEntity] = {}
    for entity in all_candidates:
        if entity.canonical_label not in best:
            best[entity.canonical_label] = entity
        else:
            existing = best[entity.canonical_label]
            if _STAGE_PRIORITY[entity.match_method] < _STAGE_PRIORITY[existing.match_method]:
                best[entity.canonical_label] = entity
    return best


def _tokens_used_by_entity(
    tokens: list[str],
    entities: dict[str, ResolvedEntity],
    high_priority_methods: frozenset[str],
) -> frozenset[int]:
    """Identify which token indices were claimed by high-priority entity matches.

    We only skip stemming for tokens that contributed to an acronym or exact
    match.  Fuzzy-matched tokens remain candidates for stemming because the
    fuzzy match may be spurious.

    WHY? A fuzzy match of e.g. "αριστοτελειου" (partial inflection of a long
    university name) with score 85 is useful as an entity hint but the same
    word is also useful as a stem.  Blocking it from stemming would lose
    information; the LLM can use both.

    Args:
        tokens: Filtered raw tokens.
        entities: Resolved entities dict (canonical_label → ResolvedEntity).
        high_priority_methods: Match methods that count as "entity claimed"
            (typically {"acronym", "exact"}).

    Returns:
        Frozenset of token indices whose text, as a window, was resolved by a
        high-priority method.  Single-token windows only (multi-token windows
        are handled by checking membership below).
    """
    # Build set of normalized single-token strings that were claimed.
    # Re-resolve each token individually to find those that fire at high priority.
    claimed_indices: set[int] = set()
    for idx, tok in enumerate(tokens):
        matches = resolve_mention(tok)
        for m in matches:
            if m.match_method in high_priority_methods:
                claimed_indices.add(idx)
                break
    return frozenset(claimed_indices)


def _collect_stems(tokens: list[str], claimed_indices: frozenset[int]) -> list[str]:
    """Stem tokens not claimed by high-priority entity resolution.

    Applies ``greek_stem`` to each unclaimed token and returns unique stems that:
      - Are at least 4 characters long (``MIN_STEM_LEN``).
      - Differ from the full normalized token (a no-op stem adds no value).

    Args:
        tokens: Filtered raw tokens.
        claimed_indices: Token indices claimed by acronym/exact entity matches.

    Returns:
        Ordered list of unique stem strings (insertion order, deduped).
    """
    from app.grounding.normalize import normalize_greek as _norm
    from app.grounding.stem import MIN_STEM_LEN

    seen: set[str] = set()
    result: list[str] = []
    for idx, tok in enumerate(tokens):
        if idx in claimed_indices:
            continue
        stem = greek_stem(tok)
        if len(stem) < MIN_STEM_LEN:
            continue
        # Skip no-op stems (stem == fully normalized token — stripping nothing).
        normalized_tok = _norm(tok)
        if stem == normalized_tok:
            continue
        if stem not in seen:
            seen.add(stem)
            result.append(stem)
    return result


def _format_entity_line(entity: ResolvedEntity) -> str:
    """Format a single entity as a markdown bullet line.

    University: ``- [University] CANONICAL_LABEL``
    Department: ``- [Department @ PARENT_UNIVERSITY] CANONICAL_LABEL``

    Args:
        entity: A resolved entity from the linker.

    Returns:
        A markdown bullet string (no trailing newline).
    """
    if entity.entity_type == "university":
        return f"- [University] {entity.canonical_label}"
    # Department — include parent university for SPARQL context.
    parent = entity.parent_university or "unknown"
    return f"- [Department @ {parent}] {entity.canonical_label}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_grounding_hints(question: str) -> str:
    """Build a grounding hint block to inject into the LLM system prompt.

    Takes a raw user question (Greek or English) and returns a formatted
    markdown string with two optional sections:

      - **Entities** — canonical KG labels resolved from the question (exact
        strings to use in SPARQL FILTER/VALUES clauses).
      - **Topic stems** — Greek word stems for CONTAINS filters.

    Returns ``""`` (empty string) when the question yields neither entities nor
    useful stems — the caller should skip injection in that case.

    Args:
        question: Raw user question, any Unicode text.  May be Greek, English,
                  or mixed.  Empty string is handled gracefully (returns "").

    Returns:
        A non-empty markdown string ready for injection, OR ``""`` if the
        grounding pipeline found nothing useful.

    Examples:
        >>> build_grounding_hints("ποια βιβλία αλγορίθμων προτείνει το ΑΠΘ;")
        '## Resolved entities & terms\\n\\n**Entities** ...'
        >>> build_grounding_hints("τι και η")
        ''
    """
    if not question.strip():
        return ""

    # Step 1 — tokenize (filter short, stopword, non-word tokens).
    tokens = _tokenize(question)
    if not tokens:
        return ""

    # Step 2 — resolve entity mentions from all unigram/bigram/trigram windows.
    entities = _resolve_all_windows(tokens)

    # Step 3 — determine which tokens are "claimed" by acronym/exact entity hits.
    high_priority = frozenset({"acronym", "exact"})
    claimed = _tokens_used_by_entity(tokens, entities, high_priority)

    # Step 4 — stem unclaimed topic words.
    stems = _collect_stems(tokens, claimed)

    # Step 5 — nothing found → bail out early.
    if not entities and not stems:
        return ""

    # Step 6 — format the output block.
    lines: list[str] = ["## Resolved entities & terms", ""]

    if entities:
        lines.append("**Entities** (use the exact label in FILTER/VALUES):")
        for entity in entities.values():
            lines.append(_format_entity_line(entity))

    if entities and stems:
        lines.append("")  # blank line between sections

    if stems:
        lines.append('**Topic stems** (use in CONTAINS(LCASE(?label), "stem")):')
        for stem in stems:
            lines.append(f"- {stem}")

    return "\n".join(lines)
