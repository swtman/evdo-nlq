"""Tests for prompt nl-to-sparql-v6 and its use by the pipeline.

Branch 1 (ADR-022): v6 forks v5 — Rule 16 treats matched titles as candidates,
the hint-usage instructions moved here from hints.py, and the {few_shot_block}
slot is restored (v5 had none, so fill() silently dropped the examples).

Branch perf/prompt-cache-static-prefix (ADR-026): the per-question grounding
hints moved from the SYSTEM prompt to the USER message (v6's
"# User (template)"), so the system prompt is byte-identical for every question
and Anthropic's prompt cache can actually be read (finding C18). Retries send
the same user message, so they keep the hints too.
"""

from unittest.mock import MagicMock

from app.llm.base import LLMResponse
from app.llm.fake_provider import FakeProvider
from app.pipeline.query_pipeline import QueryPipeline
from app.prompts.loader import load, load_user_template
from app.sparql.client import SparqlClient, SparqlResult

Q_APTH = "ποια βιβλία προτείνει το ΑΠΘ;"
Q_ALGO = "ποια βιβλία αλγορίθμων υπάρχουν;"


def _pipeline(**kw) -> QueryPipeline:
    return QueryPipeline(FakeProvider(), MagicMock(spec=SparqlClient), "fake", "fake-v1", **kw)


# --- the template -----------------------------------------------------------


def test_v6_system_has_static_slots_only() -> None:
    text = load("nl-to-sparql", 6)
    assert "{ontology_summary}" in text
    assert "{few_shot_block}" in text
    assert "{grounding_hints}" not in text  # per-question data lives in the user message


def test_v6_user_template_carries_hints_and_question() -> None:
    user = load_user_template("nl-to-sparql", 6)
    assert user is not None
    assert "{grounding_hints}" in user and "{question}" in user
    # the question first, then what grounding resolved from it (user decision)
    assert user.index("{question}") < user.index("{grounding_hints}")


def test_v5_has_no_user_template_and_keeps_hints_in_system() -> None:
    assert load_user_template("nl-to-sparql", 5) is None
    assert "{grounding_hints}" in load("nl-to-sparql", 5)


def test_v6_rule16_explains_title_candidates() -> None:
    text = load("nl-to-sparql", 6)
    assert "Title candidates" in text
    assert "Topic stems" in text
    assert "evdx:hasBook" in text  # the usage instructions moved here from hints.py
    assert "user message" in text  # and it says where the block now is


# --- the pipeline's prompt builder -----------------------------------------------


def test_system_prompt_identical_across_questions() -> None:
    """The whole point of ADR-026: one cacheable system prompt for every question."""
    pipeline = _pipeline()
    system_a, _ = pipeline._build_prompt(Q_APTH)
    system_b, _ = pipeline._build_prompt(Q_ALGO)
    assert system_a == system_b


def test_system_prompt_contains_few_shot_examples() -> None:
    system, _ = _pipeline()._build_prompt(Q_APTH)
    assert "## Examples" in system
    assert "### Example 1" in system
    assert "{few_shot_block}" not in system and "{grounding_hints}" not in system


def test_user_message_has_question_then_hints() -> None:
    _, user = _pipeline()._build_prompt(Q_APTH)
    assert user.startswith("## Question")
    assert "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" in user
    assert user.index(Q_APTH) < user.index("Resolved entities")


def test_user_message_without_hints_is_just_the_question_block() -> None:
    _, user = _pipeline()._build_prompt("τι και η")  # no entities, no stems
    assert "Resolved entities" not in user
    assert user.rstrip().endswith("τι και η")
    assert not user.startswith("\n")


def test_v5_ab_mode_keeps_its_original_layout() -> None:
    system, user = _pipeline(prompt_version=5)._build_prompt(Q_APTH)
    assert "ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" in system
    assert user == Q_APTH


def test_retry_keeps_the_hints() -> None:
    """Before ADR-026 a retry rebuilt the system prompt from the retry template
    and sent only the bare question, so the model lost every resolved label."""

    class _Recorder:
        def __init__(self) -> None:
            self.users: list[str] = []
            self.replies = iter(["NOT SPARQL AT ALL", "SELECT ?s WHERE { ?s ?p ?o }"])

        def generate(self, system, user, *, max_tokens=1024):
            self.users.append(user)
            return LLMResponse(text=next(self.replies), input_tokens=1, output_tokens=1)

    recorder = _Recorder()
    client = MagicMock(spec=SparqlClient)
    client.execute.return_value = SparqlResult(columns=[], rows=[])
    pipeline = QueryPipeline(recorder, client, "fake", "fake-v1")
    pipeline.run(Q_APTH)  # the public path: build prompt -> generate -> retry -> execute

    assert len(recorder.users) == 2  # first try + one retry
    assert all("ΑΡΙΣΤΟΤΕΛΕΙΟ ΠΑΝΕΠΙΣΤΗΜΙΟ ΘΕΣ/ΝΙΚΗΣ" in u for u in recorder.users)
