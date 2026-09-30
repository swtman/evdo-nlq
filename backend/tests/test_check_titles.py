"""Tests for scripts/check_titles.py — the offline grounding check on the title eval set (ADR-034).

The scoring is a pure function of (item, hint block), so it is tested on small hand-made hint
blocks in the exact format hints.py writes; no database, no LLM.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_titles.py"


@pytest.fixture(scope="module")
def checker():
    spec = importlib.util.spec_from_file_location("check_titles", _PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HINT = """## Resolved entities & terms

**Title candidates**:
- [Course] "ΑΝΑΛΥΣΗ ΚΥΚΛΩΜΑΤΩΝ" | "Ανάλυση Κυκλωμάτων"
- [Course] "ΑΝΑΛΥΣΗ ΚΥΚΛΩΜΑΤΩΝ Ι"
- [Book] "Ανάλυση Κυκλωμάτων και Σημάτων"

**Topic stems**:
- αναλυσ → [αά]ν[αά]λ[υύϋΰ][σς]
- κυκλωμ → κ[υύϋΰ]κλ[ωώ]μ"""


def _named(expected: str, cls: str = "course") -> dict:
    return {"id": "t", "kind": "named", "split": "dev", "class": cls, "expected_titles": [expected]}


def test_parse_hint_reads_one_norm_per_candidate_line(checker) -> None:
    parsed = checker.parse_hint(HINT)
    assert parsed["course"] == ["αναλυση κυκλωματων", "αναλυση κυκλωματων ι"]
    assert parsed["book"] == ["αναλυση κυκλωματων και σηματων"]
    assert parsed["stems"] == ["αναλυσ", "κυκλωμ"]


def test_named_title_found_and_first(checker) -> None:
    score = checker.score_item(_named("αναλυση κυκλωματων"), HINT)
    assert score["found"] and score["top1"] and not score["wrong_class"]


def test_numbered_variant_found_but_not_first(checker) -> None:
    score = checker.score_item(_named("αναλυση κυκλωματων ι"), HINT)
    assert score["found"] and not score["top1"]


def test_title_only_under_the_other_class_is_a_wrong_class_miss(checker) -> None:
    score = checker.score_item(_named("αναλυση κυκλωματων και σηματων", cls="course"), HINT)
    assert not score["found"] and score["wrong_class"]


def test_missing_title(checker) -> None:
    score = checker.score_item(_named("θεωρια πιθανοτητων"), HINT)
    assert not score["found"] and not score["top1"] and not score["wrong_class"]


def test_topic_control_counts_a_false_candidate_and_checks_stems(checker) -> None:
    item = {
        "id": "t",
        "kind": "topic-control",
        "split": "dev",
        "class": "book",
        "expected_titles": [],
        "topic_words": ["ανάλυση", "κυκλωμάτων"],
    }
    score = checker.score_item(item, HINT)
    assert score["false_candidate"] is True
    assert score["stems_ok"] is True


def test_nonexistent_title_without_candidates(checker) -> None:
    item = {
        "id": "t",
        "kind": "nonexistent",
        "split": "dev",
        "class": "course",
        "expected_titles": [],
    }
    assert (
        checker.score_item(item, "**Topic stems**:\n- υδρολογ → [υύϋΰ]δρ[οό]λ[οό]γ")[
            "false_candidate"
        ]
        is False
    )


def test_summary_has_named_and_control_tables(checker) -> None:
    scores = [
        checker.score_item(
            _named("αναλυση κυκλωματων") | {"stratum": "2–3 words", "phrasing": "bare"}, HINT
        )
    ]
    text = "\n".join(checker.summarize(scores))
    assert "| **all named** | 1 | 1/1 = 100% | 1/1 = 100% | 0/1 = 0% | 0/1 = 0% |" in text
    assert "## Controls" in text


# Branch 6 (ADR-035): a title named with a cue is listed under its own "Named titles" header.
NAMED_HINT = """## Resolved entities & terms

**Named titles**:
- [Course] "ΑΝΑΛΥΣΗ ΚΥΚΛΩΜΑΤΩΝ" | "Ανάλυση Κυκλωμάτων"

**Title candidates**:
- [Book] "Ανάλυση Κυκλωμάτων και Σημάτων"

**Topic stems**:
- σηματ → σ[ηή]μ[αά]τ"""


def test_a_family_line_counts_every_spelling_on_it(checker) -> None:
    """A title FAMILY line (ADR-024) lists the tailed variants too, and one of those may sort
    first (dev tg-020). The expected title is found if ANY surface on the line is it."""
    hint = (
        "**Named titles**:\n"
        '- [Course] "ΒΥΖΑΝΤΙΝΗ  ΦΙΛΟΛΟΓΙΑ (ΒΥΖΑΝΤΙΝΑ ΚΕΙΜΕΝΑ)" | "ΒΥΖΑΝΤΙΝΗ ΦΙΛΟΛΟΓΙΑ"\n'
        '- [Course] "Βυζαντινή Φιλολογία Ι"'
    )
    score = checker.score_item(_named("βυζαντινη φιλολογια"), hint)
    assert score["found"] and score["top1"] and score["named_firm"]
    assert not checker.score_item(_named("βυζαντινη φιλολογια ιι"), hint)["found"]


def test_parse_hint_records_the_named_section(checker) -> None:
    parsed = checker.parse_hint(NAMED_HINT)
    assert parsed["course"] == ["αναλυση κυκλωματων"]  # still a title line of its class
    assert parsed["named"] == [("course", "αναλυση κυκλωματων")]
    assert checker.parse_hint(HINT)["named"] == []


def test_named_title_under_named_section(checker) -> None:
    score = checker.score_item(
        _named("αναλυση κυκλωματων") | {"phrasing": "ονομάζεται"}, NAMED_HINT
    )
    assert score["found"] and score["named_firm"]
    assert not checker.score_item(_named("αναλυση κυκλωματων"), HINT)["named_firm"]


def test_control_with_a_named_title_is_a_firm_false_binding(checker) -> None:
    item = {
        "id": "t",
        "kind": "nonexistent",
        "split": "dev",
        "class": "course",
        "expected_titles": [],
    }
    assert checker.score_item(item, NAMED_HINT)["firm_false"] is True
    assert checker.score_item(item, HINT)["firm_false"] is False


def test_summary_reports_named_titles(checker) -> None:
    scores = [
        checker.score_item(
            _named("αναλυση κυκλωματων") | {"stratum": "2–3 words", "phrasing": "ονομάζεται"},
            NAMED_HINT,
        )
    ]
    text = "\n".join(checker.summarize(scores))
    assert "| phrasing: ονομάζεται | 1 | 1/1 = 100% | 1/1 = 100% | 0/1 = 0% | 1/1 = 100% |" in text
    assert "a Named title appears" in text


LONG_HINT = """## Resolved entities & terms

**Entities**:
- [University] ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣΣΑΛΙΑΣ
- [Department @ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣΣΑΛΙΑΣ] ΒΙΟΧΗΜΕΙΑΣ ΚΑΙ ΒΙΟΤΕΧΝΟΛΟΓΙΑΣ
- [Department @ ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ] ΒΙΟΛΟΓΙΑΣ

**Title candidates**:
- [Course] "ΚΥΤΤΑΡΙΚΗ ΒΙΟΛΟΓΙΑ"

**Topic stems**:
- κυτταρικ → κ[υύϋΰ]ττ[αά]ρ[ιίϊΐ]κ"""

UNI = "ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣΣΑΛΙΑΣ"


def _long(dept: str, dept_uni: str) -> dict:
    return {
        "id": "t",
        "kind": "long",
        "split": "dev",
        "class": "course",
        "expected_titles": ["κυτταρικη βιολογια"],
        "expected_entities": [
            {"type": "department", "label": dept, "university": dept_uni},
            {"type": "university", "label": UNI},
        ],
    }


def test_parse_hint_reads_entity_lines(checker) -> None:
    parsed = checker.parse_hint(LONG_HINT)
    assert parsed["universities"] == [UNI]
    assert ("ΒΙΟΧΗΜΕΙΑΣ ΚΑΙ ΒΙΟΤΕΧΝΟΛΟΓΙΑΣ", [UNI]) in parsed["departments"]


def test_long_question_needs_the_title_and_the_entities(checker) -> None:
    score = checker.score_item(_long("ΒΙΟΧΗΜΕΙΑΣ ΚΑΙ ΒΙΟΤΕΧΝΟΛΟΓΙΑΣ", UNI), LONG_HINT)
    assert score["found"] and score["top1"] and score["entities_ok"]


def test_department_line_must_list_the_named_university(checker) -> None:
    """ΒΙΟΛΟΓΙΑΣ is in the hint, but only at another university — not found (ADR-028)."""
    assert not checker.score_item(_long("ΒΙΟΛΟΓΙΑΣ", UNI), LONG_HINT)["entities_ok"]


def test_two_titles_found_all_versus_any(checker) -> None:
    item = {
        "id": "t",
        "kind": "two-titles",
        "split": "dev",
        "class": "course",
        "expected_titles": ["αναλυση κυκλωματων", "θεωρια πιθανοτητων"],
    }
    score = checker.score_item(item, HINT)
    assert score["found"] and not score["found_all"]


def test_title_plus_topic_checks_both(checker) -> None:
    item = {
        "id": "t",
        "kind": "title+topic",
        "split": "dev",
        "class": "course",
        "expected_titles": ["κυτταρικη βιολογια"],
        "topic_words": ["κυτταρικής"],
    }
    score = checker.score_item(item, LONG_HINT)
    assert score["found"] and score["stems_ok"]


def test_harder_table_in_summary(checker) -> None:
    scores = [checker.score_item(_long("ΒΙΟΧΗΜΕΙΑΣ ΚΑΙ ΒΙΟΤΕΧΝΟΛΟΓΙΑΣ", UNI), LONG_HINT)]
    text = "\n".join(checker.summarize(scores))
    assert "| long | 1 | 1/1 = 100% | – | 1/1 = 100% | 1/1 = 100% | – |" in text


def test_default_split_is_dev(checker) -> None:
    """Decision 3: tune on dev; test is looked at once, at the end."""
    assert checker._build_arg_parser().parse_args([]).split == "dev"
