"""Tests for app.grounding.title_index.spans — span-based title linking (branch 6, ADR-035).

Written before the implementation. They pin the design measured in S45
(notes/investigations/title-linking/scripts/s45_span_linking.py):

  - question tokens are ``title_key`` tokens (same key as the stored titles, ADR-024);
  - cue words («ονομάζεται», «με τίτλο», …) and «quotes» mark a title as NAMED (cued) and are
    never part of a span; stopwords sit inside spans but never at their edges (issue 9);
  - a span needs ≥ 2 content words unless it is cued — the single-word guard (decision 2);
    series markers count 0 (decision 4) but may end a span;
  - one candidate retrieval per class, every window aligned against it; windows score-first
    (P2), greedy non-overlapping; up to 3 titles per accepted span; threshold 0.85.

All tests use an in-memory corpus (``link_title_spans_from_corpus``) — no entities.db.
"""

from __future__ import annotations

from app.grounding.title_index.spans import (
    SpanMatch,
    SpanQuestion,
    link_title_spans_from_corpus,
    parse_question,
)

COURSES: dict[str, list[str]] = {
    "1": ["ΑΝΑΛΥΣΗ ΚΥΚΛΩΜΑΤΩΝ", "Ανάλυση Κυκλωμάτων"],
    "2": ["ΑΝΑΛΥΣΗ ΚΥΚΛΩΜΑΤΩΝ Ι"],
    "3": ["ΑΝΑΛΥΣΗ ΚΥΚΛΩΜΑΤΩΝ ΙΙ"],
    "4": ["ΑΝΑΛΥΣΗ"],
    "5": ["ΑΡΧΙΤΕΚΤΟΝΙΚΗ ΥΠΟΛΟΓΙΣΤΩΝ"],
    "6": ["ΕΙΣΑΓΩΓΗ ΣΤΟΝ ΠΡΟΓΡΑΜΜΑΤΙΣΜΟ"],
    "7": ["ΕΙΣΑΓΩΓΗ ΣΤΟ ΔΙΑΔΙΚΑΣΤΙΚΟ ΠΡΟΓΡΑΜΜΑΤΙΣΜΟ"],
    "8": ["ΠΕΤΡΟΦΥΣΙΚΗ"],
    "9": ["Αγγλικά ΙΙ Γ1"],
    "10": ["ΑΓΓΛΙΚΑ ΙΙ"],
    "11": ["ΒΑΣΕΙΣ ΔΕΔΟΜΕΝΩΝ"],
}
BOOKS: dict[str, list[str]] = {
    "1": ["Ανάλυση Κυκλωμάτων"],
    "2": ["Βάσεις Δεδομένων"],
    "3": ["Εισαγωγή στην Ψυχολογία"],
    "4": ["Η Εποχή των Αλγορίθμων"],
}
CORPORA = {"course": COURSES, "book": BOOKS}


def _link(question: str, **kw) -> list[SpanMatch]:
    return link_title_spans_from_corpus(CORPORA, parse_question(question), threshold=0.85, **kw)


def _titles(spans: list[SpanMatch], cls: str) -> list[str]:
    """First surface form of every title line of one class, in output order."""
    return [m.surface_forms[0] for s in spans if s.entity_class == cls for m in s.matches]


# ---------------------------------------------------------------------------
# parse_question — tokens, cues, quotes
# ---------------------------------------------------------------------------


def test_tokens_are_title_key_tokens() -> None:
    """«Γ1» stays one token, as in the stored key; accents/case removed; ς → σ."""
    q = parse_question("Αγγλικά ΙΙ Γ1;")
    assert q.tokens == ("αγγλικα", "ιι", "γ1")


def test_cue_words_are_marked_and_are_not_content() -> None:
    q = parse_question("μάθημα που ονομάζεται ανάλυση κυκλωμάτων")
    i = q.tokens.index("ονομαζεται")
    assert q.cue[i] and not q.content[i]
    assert q.content[q.tokens.index("αναλυση")]


def test_stopwords_markers_and_digits_are_not_content() -> None:
    q = parse_question("ποια βιβλία του μαθήματος φυσική ιι το 2022")
    content = dict(zip(q.tokens, q.content))
    assert not content["ποια"] and not content["του"] and not content["ιι"] and not content["2022"]
    assert content["φυσικη"]


def test_quoted_run_is_recorded() -> None:
    q = parse_question("ποια βιβλία προτείνει το μάθημα με τίτλο «Πετροφυσική»;")
    i = q.tokens.index("πετροφυσικη")
    assert (i, i + 1) in q.quoted


def test_parse_has_no_claims_by_default() -> None:
    assert parse_question("ΑΠΘ αναλυση κυκλωματων").claimed == frozenset()


# ---------------------------------------------------------------------------
# The original bug (F1) and cues
# ---------------------------------------------------------------------------


def test_framing_words_no_longer_hide_the_title() -> None:
    """F1: «υπάρχει … ονομάζεται» used to pull the whole-phrase score under 0.7."""
    spans = _link("σε ποιες σχολες υπαρχει μάθημα το οποιο ονομαζεται αναλυση κυκλωματων")
    course = [s for s in spans if s.entity_class == "course"]
    assert course and course[0].matches[0].surface_forms[0] == "ΑΝΑΛΥΣΗ ΚΥΚΛΩΜΑΤΩΝ"
    assert course[0].matches[0].score == 1.0
    assert course[0].cued  # right after «ονομάζεται»


def test_uncued_title_is_a_candidate() -> None:
    spans = _link("σε ποιες σχολες υπαρχει μάθημα αναλυση κυκλωματων")
    assert "ΑΝΑΛΥΣΗ ΚΥΚΛΩΜΑΤΩΝ" in _titles(spans, "course")
    assert not any(s.cued for s in spans)


def test_quoted_title_is_cued() -> None:
    spans = _link("ποια τμήματα έχουν το μάθημα «Αρχιτεκτονική Υπολογιστών»;")
    assert spans[0].cued and spans[0].matches[0].surface_forms == ["ΑΡΧΙΤΕΚΤΟΝΙΚΗ ΥΠΟΛΟΓΙΣΤΩΝ"]


def test_quoted_run_is_a_window_even_when_it_starts_with_an_article() -> None:
    """Unquoted, «η» (a stopword) cannot start a span; quoted, the user drew the edges."""
    q = parse_question("ποιος έγραψε το «Η εποχή των αλγορίθμων»;")
    spans = link_title_spans_from_corpus(CORPORA, q, threshold=0.85)
    book = [s for s in spans if s.entity_class == "book"]
    assert book and book[0].cued and q.tokens[book[0].start] == "η"
    assert book[0].matches[0].surface_forms == ["Η Εποχή των Αλγορίθμων"]


def test_article_between_cue_and_title_keeps_it_named() -> None:
    """«με τίτλο το …», «λέγεται η …»: only an article stands between cue and title (dev
    tg-114/119). The span is still cued, and it may start ON the article right after the cue,
    so a title that begins with one («Η Εποχή των Αλγορίθμων») is matched whole."""
    spans = _link("ποιος έγραψε το βιβλίο με τίτλο η εποχη των αλγοριθμων")
    book = [s for s in spans if s.entity_class == "book"]
    assert book and book[0].cued
    assert book[0].matches[0].surface_forms == ["Η Εποχή των Αλγορίθμων"]

    spans = _link("σε ποια τμήματα υπάρχει μάθημα που λέγεται η αναλυση κυκλωματων")
    course = [s for s in spans if s.entity_class == "course"]
    assert (
        course and course[0].cued and course[0].matches[0].surface_forms[0] == "ΑΝΑΛΥΣΗ ΚΥΚΛΩΜΑΤΩΝ"
    )


def test_a_cue_followed_by_no_content_word_names_nothing() -> None:
    assert _link("το βιβλίο με τίτλο το 2022") == []


def test_content_word_between_cue_and_span_ends_the_cue() -> None:
    """«ονομάζεται … » names what follows it directly — not a title further on."""
    spans = _link("μάθημα που ονομάζεται ζωροβατικο με βιβλία αρχιτεκτονικη υπολογιστων")
    assert spans and not any(s.cued for s in spans)


def test_cue_word_is_never_inside_a_span() -> None:
    q = parse_question("μαθημα που ονομαζεται αναλυση κυκλωματων")
    cue_at = q.tokens.index("ονομαζεται")
    for s in link_title_spans_from_corpus(CORPORA, q, threshold=0.85):
        assert not s.start <= cue_at < s.end


# ---------------------------------------------------------------------------
# Single-word guard (decision 2) and series markers (decision 4)
# ---------------------------------------------------------------------------


def test_single_word_is_never_a_candidate_without_a_cue() -> None:
    """ΑΝΑΛΥΣΗ is a real one-word course; a bare «ανάλυση» is a topic (stems only)."""
    assert _link("ποια βιβλία ανάλυσης προτείνονται") == []
    assert _link("ποια βιβλία έχει το μάθημα πετροφυσική") == []


def test_cued_single_word_title_is_found() -> None:
    spans = _link("ποια βιβλία προτείνει το μάθημα με τίτλο «Πετροφυσική»;")
    assert _titles(spans, "course") == ["ΠΕΤΡΟΦΥΣΙΚΗ"] and spans[0].cued


def test_cue_without_quotes_also_allows_one_word() -> None:
    spans = _link("ποια βιβλία έχει το μάθημα που λέγεται πετροφυσικη")
    assert _titles(spans, "course") == ["ΠΕΤΡΟΦΥΣΙΚΗ"]


def test_series_marker_counts_zero_content_words() -> None:
    """«αγγλικα ιι»: one content word + a marker is still one word (decision 4)."""
    assert _link("ποια βιβλία έχει το μάθημα αγγλικα ιι") == []


def test_series_marker_may_end_a_span() -> None:
    spans = _link("ποια βιβλία έχει το μάθημα αναλυση κυκλωματων ιι")
    titles = _titles(spans, "course")
    assert titles[0] == "ΑΝΑΛΥΣΗ ΚΥΚΛΩΜΑΤΩΝ ΙΙ"
    assert len(titles) <= 3  # up to 3 lines per span: the numbered siblings


def test_title_with_letters_and_digits_in_one_token() -> None:
    spans = _link("σε ποια πανεπιστήμια υπάρχει μάθημα που ονομάζεται Αγγλικά ΙΙ Γ1;")
    assert _titles(spans, "course")[0] == "Αγγλικά ΙΙ Γ1"


# ---------------------------------------------------------------------------
# Edges, selection, classes
# ---------------------------------------------------------------------------


def test_span_edges_are_content_words_or_a_final_marker() -> None:
    q = parse_question("ποια βιβλία του μαθήματος της ανάλυσης κυκλωμάτων ι προτείνονται")
    for s in link_title_spans_from_corpus(CORPORA, q, threshold=0.85):
        assert q.content[s.start]
        assert q.content[s.end - 1] or s.end - 1 > s.start


def test_stopwords_inside_a_span_are_kept() -> None:
    """«εισαγωγη στον προγραμματισμο»: «στον» is a stopword INSIDE the title."""
    spans = _link("ποια βιβλία έχει η εισαγωγη στον προγραμματισμο")
    assert _titles(spans, "course")[0] == "ΕΙΣΑΓΩΓΗ ΣΤΟΝ ΠΡΟΓΡΑΜΜΑΤΙΣΜΟ"


def test_score_first_beats_a_longer_span_with_a_framing_word() -> None:
    """P2: «διδάσκεται εισαγωγή στον προγραμματισμό» (4 content words) scores well against
    ΕΙΣΑΓΩΓΗ ΣΤΟ ΔΙΑΔΙΚΑΣΤΙΚΟ ΠΡΟΓΡΑΜΜΑΤΙΣΜΟ, but the exact 2-word span wins (S45)."""
    spans = _link("σε ποια πανεπιστήμια διδάσκεται η Εισαγωγή στον Προγραμματισμό;")
    assert _titles(spans, "course")[0] == "ΕΙΣΑΓΩΓΗ ΣΤΟΝ ΠΡΟΓΡΑΜΜΑΤΙΣΜΟ"


def test_claimed_tokens_break_spans() -> None:
    q = parse_question("αναλυση κυκλωματων")
    q = SpanQuestion(**{**q.__dict__, "claimed": frozenset({1})})
    assert link_title_spans_from_corpus(CORPORA, q, threshold=0.85) == []


def test_two_titles_in_one_question() -> None:
    spans = _link(
        "ποια βιβλία είναι κοινά στα μαθήματα αρχιτεκτονικη υπολογιστων και βασεις δεδομενων"
    )
    course = _titles(spans, "course")
    assert "ΑΡΧΙΤΕΚΤΟΝΙΚΗ ΥΠΟΛΟΓΙΣΤΩΝ" in course and "ΒΑΣΕΙΣ ΔΕΔΟΜΕΝΩΝ" in course
    starts = [s.start for s in spans]
    assert starts == sorted(starts)  # question order


def test_same_span_may_match_both_classes() -> None:
    spans = _link("ποια βιβλία έχει το μάθημα ανάλυση κυκλωμάτων")
    assert {s.entity_class for s in spans} == {"course", "book"}
    assert len({(s.start, s.end) for s in spans}) == 1


def test_classes_argument_limits_the_search() -> None:
    spans = _link("ποια βιβλία έχει το μάθημα ανάλυση κυκλωμάτων", classes=("course",))
    assert {s.entity_class for s in spans} == {"course"}


def test_threshold_rejects_a_near_title() -> None:
    assert _link("ποια βιβλία έχει το μάθημα αισθητικη κυκλωματων") == []


def test_no_content_words_no_spans() -> None:
    assert _link("ποια βιβλία έχει το μάθημα;") == []
    assert _link("") == []


def test_every_multiword_title_fed_back_as_a_question_finds_itself() -> None:
    """The one-search-path guarantee after ADR-035: a title typed exactly (≥ 2 content
    words) is found through spans, first in its class."""
    for cls, corpus in CORPORA.items():
        for surfaces in corpus.values():
            q = parse_question(surfaces[0])
            if sum(q.content) < 2:
                continue
            question = parse_question(f"ποια βιβλία έχει {surfaces[0]}")
            spans = link_title_spans_from_corpus(CORPORA, question, threshold=0.85)
            first = [s.matches[0] for s in spans if s.entity_class == cls]
            assert first and surfaces[0] in first[0].surface_forms, (cls, surfaces[0])
