"""Institution names with «και» / «&» / «,» must match exactly (branch fix/entity-name-connectors, ADR-032).

The question side drops stopwords («και») and punctuation before a name is matched
(`mentions._tokenize(…, _ENTITY_STOPWORDS)`); the exact index used to keep them
(`normalize_greek(label)`), so «τμημα βιοχημειας και βιοτεχνολογιας» could only match
ΒΙΟΧΗΜΕΙΑΣ ΚΑΙ ΒΙΟΤΕΧΝΟΛΟΓΙΑΣ fuzzily — and the exact one-word match «βιοτεχνολογιας» →
ΒΙΟΤΕΧΝΟΛΟΓΙΑΣ (another university) won. The fix gives every label a TOKEN KEY built with the
same tokenizer as the question (spellings with the same words are always listed; names that
differ by a word too short for a question — «Τ.Ε.», «Β» — only when nothing else matches), and
lets windows longer than 3 tokens match exactly. Evidence: S41 (799 pairs: 652 → 776 found, 0
regressions; the 23 left are all «Τ.Ε.»/«Β» names). These tests read the real entities.db.
"""

from app.grounding.gazetteer import get_departments, get_universities
from app.grounding.hints import build_grounding_hints
from app.grounding.lexicon import _ENTITY_STOPWORDS, _GREEK_STOPWORDS
from app.grounding.linker import resolve_exact, resolve_mention
from app.grounding.mentions import _resolve_all_windows, _tokenize
from app.grounding.normalize import content_tokens, drop_status_suffix, normalize_greek

USER_QUESTION = (
    "ποιος ειναι ο συγγραφεας του βιβλιου κυτταρικη βιολογια στο ομωνυμο μαθημα 2ου εξαμηνου "
    "στο τμημα βιοχημειας και βιοτεχνολογιας στο πανεπιστημιο θεσσαλιας"
)


def _key(text: str) -> str:
    return " ".join(content_tokens(normalize_greek(text), _ENTITY_STOPWORDS))


def _departments_in(question: str) -> set[tuple[str, str | None, str]]:
    entities = _resolve_all_windows(_tokenize(question, _ENTITY_STOPWORDS))
    return {
        (e.canonical_label, e.parent_university, e.match_method)
        for e in entities.values()
        if e.entity_type == "department"
    }


def test_user_question_grounds_the_named_department() -> None:
    """The reported question: the hint names the right department, exactly, at the right
    university — and no longer the one-word matches ΒΙΟΤΕΧΝΟΛΟΓΙΑΣ / ΧΗΜΕΙΑΣ."""
    hint = build_grounding_hints(USER_QUESTION)
    assert "- [Department @ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣΣΑΛΙΑΣ] ΒΙΟΧΗΜΕΙΑΣ ΚΑΙ ΒΙΟΤΕΧΝΟΛΟΓΙΑΣ" in hint
    assert "] ΒΙΟΤΕΧΝΟΛΟΓΙΑΣ\n" not in hint + "\n"
    assert "] ΧΗΜΕΙΑΣ\n" not in hint + "\n"
    assert "- [University] ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣΣΑΛΙΑΣ" in hint


def test_name_with_kai_matches_exactly_without_the_kai() -> None:
    """The window a question produces has no «και»; it must still match exactly."""
    found = resolve_mention("βιοχημειας βιοτεχνολογιας")
    assert [(e.canonical_label, e.match_method) for e in found] == [
        ("ΒΙΟΧΗΜΕΙΑΣ ΚΑΙ ΒΙΟΤΕΧΝΟΛΟΓΙΑΣ", "exact")
    ]


def test_ampersand_and_kai_spellings_are_both_listed() -> None:
    """«ΔΙΑΤΡΟΦΗΣ & ΔΙΑΙΤΟΛΟΓΙΑΣ» and «ΔΙΑΤΡΟΦΗΣ ΚΑΙ ΔΙΑΙΤΟΛΟΓΙΑΣ» are one name written two ways;
    the KG uses both, so the SPARQL needs both."""
    labels = {normalize_greek(e.canonical_label) for e in resolve_mention("διατροφης διαιτολογιας")}
    assert "διατροφησ & διαιτολογιασ" in labels
    assert "διατροφησ και διαιτολογιασ" in labels


def test_spelling_without_kai_does_not_hide_the_spelling_with_kai() -> None:
    """The KG has «ΠΕΡΙΦΕΡΕΙΑΚΗΣ ΚΑΙ ΟΙΚΟΝΟΜΙΚΗΣ ΑΝΑΠΤΥΞΗΣ» (Γεωπονικό) and «ΠΕΡΙΦΕΡΕΙΑΚΗΣ
    ΟΙΚΟΝΟΜΙΚΗΣ ΑΝΑΠΤΥΞΗΣ» (Στερεάς Ελλάδας). The question window equals the second one in the
    normal index; the first — same words, plus «ΚΑΙ» — must be listed too (found in S41: the
    one miss a pure "token key only as fallback" rule left)."""
    found = {
        (e.canonical_label, e.parent_university)
        for e in resolve_mention("περιφερειακης οικονομικης αναπτυξης")
    }
    assert ("ΠΕΡΙΦΕΡΕΙΑΚΗΣ ΚΑΙ ΟΙΚΟΝΟΜΙΚΗΣ ΑΝΑΠΤΥΞΗΣ", "ΓΕΩΠΟΝΙΚΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΑΘΗΝΩΝ") in found
    assert any(label.startswith("ΠΕΡΙΦΕΡΕΙΑΚΗΣ ΟΙΚΟΝΟΜΙΚΗΣ ΑΝΑΠΤΥΞΗΣ") for label, _ in found)


def test_name_longer_than_three_words_matches_exactly_in_a_question() -> None:
    """Windows used to stop at 3 tokens; longer names can now match exactly (exact-only
    lookups, no fuzzy cost)."""
    found = _departments_in(
        "ποια μαθηματα εχει το τμημα γεωπονιας ιχθυολογιας και υδατινου περιβαλλοντος"
    )
    assert any(
        label == "ΓΕΩΠΟΝΙΑΣ ΙΧΘΥΟΛΟΓΙΑΣ ΚΑΙ ΥΔΑΤΙΝΟΥ ΠΕΡΙΒΑΛΛΟΝΤΟΣ" and method == "exact"
        for label, _, method in found
    )


def test_university_name_with_kai_matches_exactly() -> None:
    found = resolve_mention("παντειο πανεπιστημιο κοινωνικων πολιτικων επιστημων")
    assert ("ΠΑΝΤΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΚΟΙΝΩΝΙΚΩΝ ΚΑΙ ΠΟΛΙΤΙΚΩΝ ΕΠΙΣΤΗΜΩΝ", "exact") in {
        (e.canonical_label, e.match_method) for e in found
    }


def test_plain_names_are_not_widened() -> None:
    """The tokenizer drops words under 3 letters, so «ΝΟΣΗΛΕΥΤΙΚΗΣ Β» and «… Τ.Ε.» share a token
    key with the plain name. Their spelling keys differ (the short word is kept there), so a
    plain name keeps its own departments only."""
    nursing = {e.canonical_label for e in resolve_mention("νοσηλευτικης")}
    assert not any(label.startswith("ΝΟΣΗΛΕΥΤΙΚΗΣ Β") for label in nursing)
    mech = {e.canonical_label for e in resolve_mention("μηχανολογων μηχανικων")}
    assert mech and not any("Τ.Ε." in label for label in mech)


def test_resolve_exact_never_runs_the_fuzzy_stage() -> None:
    """Long windows are looked up with resolve_exact: hash lookups only."""
    assert resolve_mention("βιοχημειας")  # fuzzy finds something …
    assert resolve_exact("βιοχημειας") == []  # … the exact-only lookup does not


def test_every_label_typed_in_a_question_resolves_to_its_own_name() -> None:
    """Symmetry: for every university and department label, the words a question would carry
    resolve exactly to an entity with the same token key (the label itself, another spelling of
    it, or — for «Τ.Ε.»/«Β» names — the plain name the question cannot tell apart)."""
    labels = set(get_universities()) | {d["department"] for d in get_departments()}
    for label in labels:
        typed = " ".join(_tokenize(drop_status_suffix(label).lower(), _ENTITY_STOPWORDS))
        found = resolve_exact(typed)
        assert found, label
        assert any(_key(e.canonical_label) == _key(label) for e in found), label


def test_content_tokens_is_the_tokenizer_core() -> None:
    """`_tokenize` delegates to `content_tokens`; without series markers they are identical."""
    for question in (
        USER_QUESTION,
        "Ποια βιβλία αλγορίθμων προτείνει το ΑΠΘ;",
        "ΑΝΑΛΥΣΗ ΚΥΚΛΩΜΑΤΩΝ ΙΙ 2022",
    ):
        for stopwords in (_ENTITY_STOPWORDS, _GREEK_STOPWORDS):
            assert _tokenize(question, stopwords) == content_tokens(question, stopwords)
