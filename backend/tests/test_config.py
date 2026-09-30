from app.config import settings


def test_settings_has_required_fields():
    assert hasattr(settings, "llm_provider")
    assert hasattr(settings, "llm_model")
    assert hasattr(settings, "graphdb_endpoint")
    assert hasattr(settings, "llm_cache_dir")
    assert hasattr(settings, "llm_cache_disabled")
    assert hasattr(settings, "frontend_origin")
    assert hasattr(settings, "log_level")
    assert hasattr(settings, "course_linking_enabled")
    assert hasattr(settings, "book_linking_enabled")
    assert hasattr(settings, "title_span_threshold")


def test_settings_defaults():
    assert settings.llm_provider == "claude"
    assert settings.llm_model == "claude-haiku-4-5"
    assert "EvdoGraph" in settings.graphdb_endpoint
    assert settings.llm_cache_dir == ".llm_cache"
    assert settings.llm_cache_disabled is False


def test_book_linking_defaults_match_course_linking():
    # Book linking ships enabled by default, mirroring course linking, so
    # the feature is exercised from day one rather than shipping dark.
    assert settings.book_linking_enabled is True
    assert settings.course_linking_enabled is True


def test_title_span_threshold_default():
    # Branch 6 (ADR-035): one threshold for span-based title linking, 0.85 as measured
    # in S45 (0.80 lets every nonexistent dev title through, 0.90 loses recall). The
    # per-class whole-phrase thresholds (0.7) went away with the whole-phrase ranking.
    assert settings.title_span_threshold == 0.85
    assert not hasattr(settings, "course_match_threshold")
    assert not hasattr(settings, "book_match_threshold")
