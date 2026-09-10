"""Greek lexicon data for the grounding orchestrator — pure data, no logic.

Stopword sets, institution/glue-word sets, and the vowel-accenting table used
by ``hints.py`` to tokenize questions and format hint output. Split out
(ADR-021) from ``hints.py`` as its own module because none of it depends on
the tokenization, entity-selection, or rendering logic that consumes it.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Greek stopwords (normalized form — accent-free, lowercase, ς→σ)
# ---------------------------------------------------------------------------

_GREEK_STOPWORDS: frozenset[str] = frozenset(
    {
        # Articles
        "ο",
        "η",
        "το",
        "οι",
        "τα",
        "τον",
        "την",
        "τησ",
        "του",
        "των",
        "τοισ",
        "ταισ",
        # Prepositions
        "σε",
        "στο",
        "στη",
        "στον",
        "στην",
        "στα",
        "απο",
        "για",
        "στισ",
        "απ",
        "μεσ",
        "με",
        "κατα",
        "προσ",
        "ωσ",
        "περι",
        # Conjunctions
        "και",
        "η",
        "αλλα",
        "ομωσ",
        "ενω",
        "οτι",
        "που",
        "πωσ",
        # Pronouns
        "εγω",
        "εσυ",
        "αυτοσ",
        "αυτη",
        "αυτο",
        "αυτοι",
        "αυτεσ",
        "αυτα",
        "ποιοσ",
        "ποια",
        "ποιο",
        # Common verbs
        "ειναι",
        "εχει",
        "εχουν",
        "ειχε",
        "εχω",
        "θελω",
        # Question words (all case forms so residual phrase stays clean for title ranking)
        "ποια",
        "ποιοσ",
        "ποιεσ",
        "ποιων",
        "ποσα",
        "ποτε",
        "που",
        "πωσ",
        "γιατι",
        "ποιουσ",  # acc pl. masc. "ποιους" — e.g. "ποιους καθηγητές ..."
        # Attribute/role nouns (what the user is ASKING for, not part of the title)
        # Filtering these keeps the title-ranking phrase clean.
        "καθηγητεσ",
        "καθηγητη",
        "καθηγητησ",
        "καθηγητεσ",  # professor (various cases)
        "συγγραφεασ",
        "συγγραφεισ",
        "συγγραφεα",  # author
        "εκδοτησ",
        "εκδοτεσ",  # publisher
        # Common domain nouns (too generic to be useful stems)
        "βιβλια",
        "βιβλιο",
        "μαθημα",
        "μαθηματα",
        "κουρσα",
        "κορσα",
        "τμημα",
        "πανεπιστημιο",
        "τεχνολογικο",
        "ιδρυμα",
        "σχολη",
        "σχολεσ",
        "σχολων",
        "ετοσ",
        "χρονια",
        # Numbers as words
        "ενα",
        "δυο",
        "τρια",
        "τεσσερα",
    }
)

# Institution-type words that are stopwords for topic stemming but must be
# KEPT for entity disambiguation.  E.g. "πανεπιστημιο" in the phrase
# "πανεπιστημιο πειραια" distinguishes ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΕΙΡΑΙΩΣ from ΤΕΙ ΠΕΙΡΑΙΑ;
# stripping it first causes the bare "πειραια" unigram to match ΤΕΙ (score 90)
# instead of the University (score 92.7 for the full bigram).
_INSTITUTION_WORDS: frozenset[str] = frozenset(
    {
        "πανεπιστημιο",
        "τμημα",
        "σχολη",
        "σχολεσ",
        "σχολων",
        "τεχνολογικο",
        "ιδρυμα",
    }
)

# Stopword set for entity tokenization — identical to _GREEK_STOPWORDS but
# retaining institution words so multi-word university fragments survive as
# sliding windows for the entity linker.
_ENTITY_STOPWORDS: frozenset[str] = _GREEK_STOPWORDS - _INSTITUTION_WORDS

# Glue-only words: tokens that carry NO discriminating entity information on
# their own.  A bare "πανεπιστημιο" unigram partial-matches every
# "ΠΑΝΕΠΙΣΤΗΜΙΟ X" at ~100 via rapidfuzz partial_ratio, injecting a random
# university.  Windows whose tokens are ALL glue words are skipped.
# Multi-word windows that merely *contain* a glue word ("πανεπιστημιο πειραια")
# are kept — they have a discriminating non-glue token ("πειραια").
#
# THIS GUARD IS LOAD-BEARING SPECIFICALLY FOR ``fuzz.WRatio`` (linker.py's
# Stage 3 scorer, also used by title_index.search.rank_titles(entity_class=
# "university"/"department") — see ADR-020).  WRatio's partial-matching
# behaviour is exactly what makes a bare glue word dangerous: measured
# against the real 46 university labels, a bare "πανεπιστημιο" scores >=90
# against 13 of them under WRatio, vs. 0 of them under token_sort_ratio (the
# scorer course/book titles use, which does NOT reward partial matches).  If
# a future refactor ever swaps the institution scorer to something
# order/whole-string-based, this guard becomes unnecessary — but as long as
# WRatio is in play here, deleting it reintroduces the random-university bug.
_INSTITUTION_GLUE: frozenset[str] = _INSTITUTION_WORDS | frozenset(
    {
        "πολυτεχνειο",
        "τει",
        "ανωτατο",
        "ανωτατη",
    }
)

# The KG stores titles in both ALL-CAPS accent-free ("ΑΛΓΟΡΙΘΜΟΙ") and
# mixed-case accented ("Αλγόριθμοι"). SPARQL's LCASE() strips case but NOT
# Unicode accents, so CONTAINS(LCASE("Αλγόριθμοι"), "αλγορ") is false because
# ό (U+03CC) ≠ ο (U+03BF). We emit both the plain stem and the version with
# the last vowel accented to cover both storage styles in one FILTER.
_GREEK_VOWELS_STR: str = "αεηιουω"
_VOWEL_TO_ACCENTED: dict[int, str] = str.maketrans("αεηιουω", "άέήίόύώ")

# Display label per TitleMatch.entity_class — keys must match schema.TITLE_CLASSES.
_TITLE_CLASS_LABELS: dict[str, str] = {"course": "Course", "book": "Book"}
