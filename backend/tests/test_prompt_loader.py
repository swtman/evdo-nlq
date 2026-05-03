import pytest
import app.prompts.loader as loader_module
from app.prompts.loader import load, fill


@pytest.fixture(autouse=True)
def clear_prompt_cache():
    """Reset the module-level cache before each test to ensure isolation."""
    loader_module._cache.clear()
    yield
    loader_module._cache.clear()


def test_load_returns_system_section_of_nl_to_sparql_v1():
    """The real nl-to-sparql-v1.md must be present in prompts/."""
    text = load("nl-to-sparql", 1)
    assert "{ontology_summary}" in text
    assert "SPARQL" in text
    # Should NOT include the User or Notes sections
    assert "# User" not in text
    assert "# Notes" not in text


def test_load_raises_for_missing_file():
    with pytest.raises(FileNotFoundError):
        load("nonexistent-prompt", 99)


def test_fill_substitutes_known_slots():
    template = "Hello {name}, you asked: {question}"
    result = fill(template, name="World", question="ποια βιβλία;")
    assert result == "Hello World, you asked: ποια βιβλία;"


def test_fill_leaves_unknown_slots_unchanged():
    """SPARQL curly braces and unrecognised slots must not be consumed."""
    template = "WHERE { ?s ?p ?o } {unknown_slot}"
    result = fill(template, known="value")
    assert "{ ?s ?p ?o }" in result
    assert "{unknown_slot}" in result


def test_fill_handles_sparql_word_braces():
    template = "FILTER (?year >= 2020) {ontology_summary}"
    result = fill(template, ontology_summary="schema here")
    assert "FILTER (?year >= 2020)" in result
    assert "schema here" in result


def test_load_is_cached_after_first_read(monkeypatch):
    """Second call must return the same result without re-reading disk."""
    first = load("nl-to-sparql", 1)
    # Poison the prompts dir so any disk read would raise FileNotFoundError
    monkeypatch.setattr(loader_module, "_PROMPTS_DIR", loader_module._PROMPTS_DIR / "nonexistent")
    second = load("nl-to-sparql", 1)
    assert first == second  # served from cache, no FileNotFoundError
