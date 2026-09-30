"""Tests for app.grounding.hints — the grounding orchestrator.

Tests are written before the implementation (TDD).  They verify:
  - Empty / stopword-only input returns exactly "".
  - Acronym entity detection produces the expected canonical label and type tag.
  - Topic stemming produces the expected stem and section header.
  - Combined entity + stem questions produce both sections.
  - The return value is exactly "" (not whitespace) when nothing fires.
"""

from app.grounding.hints import build_grounding_hints


# ---------------------------------------------------------------------------
# Empty / no-entity-no-stem cases
# ---------------------------------------------------------------------------


def test_empty_question_returns_empty() -> None:
    """Empty string must return exactly '' — the pipeline skips injection."""
    assert build_grounding_hints("") == ""


def test_no_entity_no_stem_returns_empty() -> None:
    """Question containing only stopwords or short tokens must return ''."""
    assert build_grounding_hints("τι και η") == ""


def test_returns_empty_string_not_whitespace() -> None:
    """Return value must be '' not '\\n' or '  ' when nothing is found."""
    result = build_grounding_hints("και η το")
    assert result == ""


# ---------------------------------------------------------------------------
# Entity detection
# ---------------------------------------------------------------------------


def test_apth_acronym_detected() -> None:
    """ΑΠΘ must resolve to its canonical label via the acronym stage."""
    result = build_grounding_hints("ποια βιβλία προτείνει το ΑΠΘ;")
    assert "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" in result
    assert "[University]" in result


def test_entities_section_header_present_when_entity_found() -> None:
    """Resolved entities section header must appear when at least one entity fires."""
    result = build_grounding_hints("ΑΠΘ")
    assert "Entities" in result


# ---------------------------------------------------------------------------
# Topic stem detection
# ---------------------------------------------------------------------------


def test_stem_in_result() -> None:
    """'αλγοριθμων' (genitive) must produce stem 'αλγορ'."""
    result = build_grounding_hints("βιβλία αλγοριθμων")
    assert "αλγορ" in result
    assert "Topic stems" in result


def test_no_entities_only_stem() -> None:
    """When only stems fire (no recognized entity), the entity section is absent."""
    result = build_grounding_hints("βιβλία αλγοριθμων")
    assert "[University]" not in result
    assert "αλγορ" in result


# ---------------------------------------------------------------------------
# Combined entity + stem
# ---------------------------------------------------------------------------


def test_combined_entity_and_stem() -> None:
    """Both sections must appear when the question has an entity AND a topic word."""
    result = build_grounding_hints("ποια βιβλία αλγορίθμων προτείνει το ΑΠΘ;")
    assert "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" in result
    assert "αλγορ" in result
    assert "Entities" in result
    assert "Topic stems" in result


# ---------------------------------------------------------------------------
# Format / structure checks
# ---------------------------------------------------------------------------


def test_entity_section_absent_when_no_entity() -> None:
    """'Entities' section header must NOT appear when no entity resolves.

    'αλγοριθμων' and 'κβαντικων' are topic words that do not match any
    university or department in the EvdoGraph KG gazetteer.
    """
    result = build_grounding_hints("αλγοριθμων κβαντικων")
    # Neither word is a KG entity name — only stems should appear.
    assert "Entities" not in result


def test_stem_section_absent_when_no_stem() -> None:
    """'Topic stems' section must NOT appear when only entities fire and no useful stems."""
    # ΑΠΘ itself: 3 chars after normalization — filtered before stemming even runs.
    # The stopwords filter should eliminate "ποια", "το"; no non-entity non-stopword
    # long-enough tokens remain to produce stems.
    result = build_grounding_hints("το ΑΠΘ")
    # ΑΠΘ resolves as entity; no other tokens long enough for stemming
    assert "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" in result
    assert "Topic stems" not in result


def test_output_starts_with_section_heading() -> None:
    """Non-empty output must start with the markdown '## Resolved entities' heading."""
    result = build_grounding_hints("ΑΠΘ αλγοριθμων")
    assert result.startswith("## Resolved entities")


def test_stem_bullet_contains_stem() -> None:
    """Each stem must appear as a bullet line '- <stem>'."""
    result = build_grounding_hints("αλγοριθμων")
    lines = result.splitlines()
    # At least one line matches "- <something>"
    bullet_lines = [ln for ln in lines if ln.startswith("- ")]
    assert any("αλγορ" in ln for ln in bullet_lines)


def test_university_entity_format() -> None:
    """University entities use the '[University] CANONICAL_LABEL' format."""
    result = build_grounding_hints("ΑΠΘ")
    assert "- [University] ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" in result


def test_stem_bullet_has_vowel_class_pattern() -> None:
    """Stem bullets show 'stem → pattern' so one REGEX covers every KG storage form.

    The KG stores some titles in ALL-CAPS accent-free ("ΑΛΓΟΡΙΘΜΟΙ") and others
    in mixed-case accented ("Αλγόριθμοι"). SPARQL LCASE() strips case but not
    accents, and the old 'stem | stém' pair accented only the LAST vowel, which
    misses «αλγόριθμος» (C5; S40a: 35 vs 81 rows on ex-024). A vowel class per
    vowel matches wherever the accent sits (ADR-031).
    """
    result = build_grounding_hints("αλγοριθμων")
    assert "- αλγοριθμ → [αά]λγ[οό]ρ[ιίϊΐ]θμ" in result
    assert " | αλγ" not in result  # the old accented pair is gone


def test_word_without_a_stripped_ending_still_gets_a_stem() -> None:
    """Bug F2: «αναλυση» was left unchanged by greek_stem and then dropped as a
    'no-op'; the topic vanished from the hint. Snowball stems it, and a stem equal
    to the whole word is no longer dropped either."""
    result = build_grounding_hints("βιβλια για αναλυση")
    assert "- αναλυσ → " in result


def test_latin_content_word_becomes_a_stem() -> None:
    """English words in a Greek question (the KG has English titles) used to be
    dropped as no-op stems; now they are listed, pattern unchanged."""
    result = build_grounding_hints("βιβλια για python")
    assert "- python → python" in result


# ---------------------------------------------------------------------------
# Grounding fix #1 — institution-word disambiguation
# ---------------------------------------------------------------------------


def test_panepistimio_peiraia_resolves_to_university_not_tei() -> None:
    """Explicitly naming 'πανεπιστημιο' must route to ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΕΙΡΑΙΩΣ.

    Root cause of the old bug: 'πανεπιστημιο' was stripped as a topic stopword,
    leaving only the bare 'πειραια' unigram which scores 90 for ΤΕΙ ΠΕΙΡΑΙΑ
    (verbatim substring match) but only 77 for ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΕΙΡΑΙΩΣ.  The fix
    keeps institution words for entity matching so the bigram
    'πανεπιστημιο πειραια' (score 92.7) beats the ΤΕΙ unigram.
    """
    result = build_grounding_hints(
        "Τι συγγράμματα οικονομικών διδάσκονται στο πανεπιστημιο πειραια;"
    )
    assert "ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΕΙΡΑΙΩΣ" in result
    assert "ΤΕΙ ΠΕΙΡΑΙΑ" not in result


def test_panepistimio_peiraia_accented_resolves_to_university_not_tei() -> None:
    """Accented variant 'Πανεπιστήμιο Πειραιά' must also resolve correctly."""
    result = build_grounding_hints(
        "Τι συγγράμματα οικονομικών διδάσκονται στο Πανεπιστήμιο Πειραιά;"
    )
    assert "ΠΑΝΕΠΙΣΤΗΜΙΟ ΠΕΙΡΑΙΩΣ" in result
    assert "ΤΕΙ ΠΕΙΡΑΙΑ" not in result


def test_two_acronyms_both_retained() -> None:
    """Both ΑΠΘ and ΕΚΠΑ must appear — greedy selection must not suppress either.

    Both are acronym unigrams (highest priority).  Non-overlapping spans mean
    both are accepted; no fuzzy bigram should displace them.
    """
    result = build_grounding_hints("ΑΠΘ και ΕΚΠΑ")
    assert "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" in result
    assert "ΕΘΝΙΚΟ & ΚΑΠΟΔΙΣΤΡΙΑΚΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΑΘΗΝΩΝ" in result


def test_bare_panepistimio_emits_no_university() -> None:
    """A lone 'πανεπιστημιο' with no discriminating city token must emit nothing.

    The glue guard skips all-glue-word windows; the unigram 'πανεπιστημιο' would
    otherwise partial-match every 'ΠΑΝΕΠΙΣΤΗΜΙΟ X' at ~100 and inject a random
    university.
    """
    result = build_grounding_hints("πανεπιστημιο")
    assert "[University]" not in result


# ---------------------------------------------------------------------------
# Title lines (branch 6, ADR-035). ``link_title_spans`` is monkeypatched so these
# tests exercise the SECTIONS and FORMATTING only, independent of entities.db (the
# span linker has its own suite, tests/test_title_spans.py). Its fake receives the
# analysed question (a SpanQuestion) and returns SpanMatch objects.
#
# The question is made of non-words so it cannot resolve as an entity.
# ---------------------------------------------------------------------------

import app.grounding.hints as hints_module  # noqa: E402
from app.grounding.title_index import TitleMatch  # noqa: E402
from app.grounding.title_index.spans import SpanMatch  # noqa: E402

_NONSENSE_QUESTION = "ζωροβατικη μελετη ξενοφωνικης"  # tokens 0, 1, 2


def _course_match(norm="ζωροβατικη μελετη", score=0.9, surfaces=None):
    return TitleMatch(
        normalized_title=norm, score=score,
        surface_forms=surfaces or [f"{norm.upper()}"], entity_class="course",
    )


def _book_match(norm="ξενοφωνικης θεωριας", score=0.9, surfaces=None):
    return TitleMatch(
        normalized_title=norm, score=score,
        surface_forms=surfaces or [f"{norm.upper()}"], entity_class="book",
    )


def _span(match, start=0, end=2, cued=False):
    return SpanMatch(start=start, end=end, cued=cued, entity_class=match.entity_class,
                     matches=[match])


def _fake(*spans):
    """A link_title_spans stand-in that honours the ``classes`` argument."""

    def fake_link(question, *, threshold, classes):
        return [s for s in spans if s.entity_class in classes]

    return fake_link


def test_course_only_match_formats_with_course_tag(monkeypatch) -> None:
    monkeypatch.setattr(hints_module, "link_title_spans", _fake(_span(_course_match())))
    result = build_grounding_hints(_NONSENSE_QUESTION)

    assert "[Course]" in result
    assert "[Book]" not in result
    assert "matched BOTH" not in result


def test_book_only_match_formats_with_book_tag(monkeypatch) -> None:
    monkeypatch.setattr(hints_module, "link_title_spans", _fake(_span(_book_match(), 2, 3)))
    result = build_grounding_hints(_NONSENSE_QUESTION)

    assert "[Book]" in result
    assert "[Course]" not in result
    assert "matched BOTH" not in result


def test_different_titles_both_classes_no_collision_note(monkeypatch) -> None:
    """Course matches title A, book matches a DIFFERENT title B — both lines
    render, but no note: two different titles matching is not an ambiguity,
    and a note there would be factually false."""
    monkeypatch.setattr(
        hints_module, "link_title_spans",
        _fake(_span(_course_match()), _span(_book_match(), 2, 3)),
    )
    result = build_grounding_hints(_NONSENSE_QUESTION)

    assert "[Course]" in result
    assert "[Book]" in result
    assert "matched BOTH" not in result


def test_same_title_both_classes_emits_collision_note(monkeypatch) -> None:
    """The SAME normalized title matching both classes must emit both lines
    AND the collision note, naming the colliding title."""
    norm, surface = "ιδια τιτλος", "ΙΔΙΑ ΤΙΤΛΟΣ"
    monkeypatch.setattr(
        hints_module, "link_title_spans",
        _fake(_span(_course_match(norm=norm, surfaces=[surface])),
              _span(_book_match(norm=norm, surfaces=[surface]))),
    )
    result = build_grounding_hints(_NONSENSE_QUESTION)

    assert "[Course]" in result
    assert "[Book]" in result
    assert "matched BOTH a Course and a Book" in result
    assert "ΙΔΙΑ ΤΙΤΛΟΣ" in result  # names the colliding title


def test_surface_forms_joined_with_pipe(monkeypatch) -> None:
    monkeypatch.setattr(
        hints_module, "link_title_spans",
        _fake(_span(_course_match(surfaces=["ΑΛΦΑ ΒΗΤΑ", "Άλφα Βήτα"]))),
    )
    result = build_grounding_hints(_NONSENSE_QUESTION)

    assert '"ΑΛΦΑ ΒΗΤΑ" | "Άλφα Βήτα"' in result


def test_book_linking_disabled_suppresses_book_search(monkeypatch) -> None:
    seen: list[tuple[str, ...]] = []

    def fake_link(question, *, threshold, classes):
        seen.append(classes)
        return [s for s in (_span(_course_match()), _span(_book_match(), 2, 3))
                if s.entity_class in classes]

    monkeypatch.setattr(hints_module, "link_title_spans", fake_link)
    monkeypatch.setattr(hints_module.settings, "book_linking_enabled", False)
    result = build_grounding_hints(_NONSENSE_QUESTION)

    assert seen == [("course",)]
    assert "[Book]" not in result


def test_span_threshold_comes_from_settings(monkeypatch) -> None:
    seen: list[float] = []

    def fake_link(question, *, threshold, classes):
        seen.append(threshold)
        return []

    monkeypatch.setattr(hints_module, "link_title_spans", fake_link)
    monkeypatch.setattr(hints_module.settings, "title_span_threshold", 0.91)
    build_grounding_hints(_NONSENSE_QUESTION)
    assert seen == [0.91]


def test_linker_receives_the_analysed_question(monkeypatch) -> None:
    seen = []

    def fake_link(question, *, threshold, classes):
        seen.append(question)
        return []

    monkeypatch.setattr(hints_module, "link_title_spans", fake_link)
    build_grounding_hints("ζωροβατικη μελετη ιι")
    assert seen and seen[0].tokens == ("ζωροβατικη", "μελετη", "ιι")


# ---------------------------------------------------------------------------
# Decision 1: an UN-cued title is a candidate (stems kept); a CUED one is named
# (firm, own section, no stems for its words). Branch 1 + branch 6.
# ---------------------------------------------------------------------------


def _stem_lines(result: str) -> str:
    return result.split("**Topic stems**")[-1] if "**Topic stems**" in result else ""


def test_stems_kept_when_title_candidate_present(monkeypatch) -> None:
    """A title candidate must NOT swallow the topic stems (ex-024 regression:
    'βιβλία αλγορίθμων' bound ΘΕΩΡΙΑ ΑΛΓΟΡΙΘΜΩΝ and lost the 'αλγορ' stem)."""
    monkeypatch.setattr(hints_module, "link_title_spans", _fake(_span(_course_match())))
    result = build_grounding_hints(_NONSENSE_QUESTION)

    assert "[Course]" in result
    assert "ζωροβατικ" in _stem_lines(result)  # a word of the candidate span
    assert "ξενοφωνικ" in _stem_lines(result)


def test_title_section_is_labelled_candidates(monkeypatch) -> None:
    monkeypatch.setattr(hints_module, "link_title_spans", _fake(_span(_course_match())))
    result = build_grounding_hints(_NONSENSE_QUESTION)

    assert "**Title candidates**" in result
    assert "**Named titles**" not in result
    assert "Resolved title(s)" not in result


def test_cued_span_goes_to_named_titles(monkeypatch) -> None:
    monkeypatch.setattr(hints_module, "link_title_spans",
                        _fake(_span(_course_match(), cued=True)))
    result = build_grounding_hints(_NONSENSE_QUESTION)

    assert "**Named titles**:" in result
    assert "**Title candidates**" not in result
    named = result.split("**Named titles**:")[1].split("**Topic stems**")[0]
    assert "[Course]" in named


def test_cued_span_words_get_no_stems(monkeypatch) -> None:
    """A named title's words are the title, not a topic — only the other words stem."""
    monkeypatch.setattr(hints_module, "link_title_spans",
                        _fake(_span(_course_match(), 0, 2, cued=True)))
    stems = _stem_lines(build_grounding_hints(_NONSENSE_QUESTION))

    assert "ζωροβατικ" not in stems and "μελετ" not in stems
    assert "ξενοφωνικ" in stems


def test_named_section_comes_before_candidates(monkeypatch) -> None:
    monkeypatch.setattr(
        hints_module, "link_title_spans",
        _fake(_span(_course_match(), 0, 2, cued=True), _span(_book_match(), 2, 3)),
    )
    result = build_grounding_hints(_NONSENSE_QUESTION)
    assert result.index("**Named titles**") < result.index("**Title candidates**")


def test_hint_block_carries_no_usage_instructions(monkeypatch) -> None:
    """Usage instructions belong to the versioned prompt (Rule 16), not to text
    inlined in hints.py — so the old instruction phrases are gone."""
    norm, surface = "ιδια τιτλος", "ΙΔΙΑ ΤΙΤΛΟΣ"
    monkeypatch.setattr(
        hints_module, "link_title_spans",
        _fake(_span(_course_match(norm=norm, surfaces=[surface]), cued=True),
              _span(_book_match(norm=norm, surfaces=[surface]))),
    )
    result = build_grounding_hints(_NONSENSE_QUESTION + " ΑΠΘ")

    for phrase in ("do NOT use CONTAINS", "use the exact label in FILTER/VALUES",
                   "use in CONTAINS(LCASE", "Bind only the class", "evdx:hasBook"):
        assert phrase not in result, phrase


# ---------------------------------------------------------------------------
# Branch 6 end to end on the real entities.db (no monkeypatch): cues, cue words,
# the department cue.
# ---------------------------------------------------------------------------


def test_f1_question_names_the_title() -> None:
    """The question that started the investigation (F1): framing words and «ονομάζεται»."""
    result = build_grounding_hints(
        "σε ποιες σχολες υπαρχει μάθημα το οποιο ονομαζεται αναλυση κυκλωματων"
    )
    named = result.split("**Named titles**:")[1] if "**Named titles**:" in result else ""
    assert '"ΑΝΑΛΥΣΗ ΚΥΚΛΩΜΑΤΩΝ"' in named.split("**")[0]


def test_cue_words_never_become_stems() -> None:
    stems = _stem_lines(build_grounding_hints("μαθημα που ονομαζεται ζωροβατικη μελετη"))
    assert "ονομαζ" not in stems


def test_department_word_without_cue_keeps_its_stem() -> None:
    """«φυσικής» here is a topic (ADR-034 finding: 1/4 one-word topics kept a stem)."""
    stems = _stem_lines(build_grounding_hints("ποια βιβλία φυσικής προτείνει το ΕΚΠΑ;"))
    assert "φυσικ" in stems


def test_department_after_cue_is_claimed() -> None:
    """After «Τμήμα» the words are the department: no stem, no title span."""
    result = build_grounding_hints(
        "Πόσα μαθήματα προσέφερε το Τμήμα Φυσικής του Πανεπιστημίου Πατρών το 2022;"
    )
    assert "φυσικ" not in _stem_lines(result)
    assert "Title candidates" not in result and "Named titles" not in result
    assert "ΦΥΣΙΚΗΣ" in result  # the entity line is still there


def test_multiword_department_after_cue_is_not_a_title() -> None:
    result = build_grounding_hints(
        "Πόσα μαθήματα είχε το 2022 το Τμήμα Οικονομικών Επιστημών του Πανεπιστημίου Πελοποννήσου;"
    )
    assert "Title candidates" not in result and "Named titles" not in result
    assert "ΟΙΚΟΝΟΜΙΚΩΝ ΕΠΙΣΤΗΜΩΝ" in result


# ---------------------------------------------------------------------------
# Branch 2 (fix/keep-roman-numeral-tokens) — series-marker tokens (decision 4).
# ---------------------------------------------------------------------------

from app.grounding.mentions import _tokenize  # noqa: E402


# (Branch 2's keep_series_markers tests were removed in branch 6: titles no longer use
# _tokenize — markers in title spans are covered by tests/test_title_spans.py.)


def test_tokenize_default_unchanged() -> None:
    """Entity tokens: markers, years and short words are dropped, as before."""
    assert _tokenize("αναλυση κυκλωματων ι 2") == ["αναλυση", "κυκλωματων"]


def test_markers_never_become_stems() -> None:
    result = build_grounding_hints("ξενοφωνικης ιι 2")
    stem_lines = result.split("**Topic stems**")[-1] if "**Topic stems**" in result else ""
    for marker in ("- ιι", "- 2"):
        assert marker not in stem_lines


def test_four_letter_marker_never_becomes_a_stem() -> None:
    """«VIII» is 4 letters, so the length guard does not stop it; before branch 4
    the no-op rule did. Series markers are now skipped explicitly."""
    result = build_grounding_hints("ξενοφωνικης VIII")
    stem_lines = result.split("**Topic stems**")[-1] if "**Topic stems**" in result else ""
    assert "viii" not in stem_lines.lower()
