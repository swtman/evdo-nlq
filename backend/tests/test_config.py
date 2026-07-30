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
    assert hasattr(settings, "course_match_threshold")
    assert hasattr(settings, "book_linking_enabled")
    assert hasattr(settings, "book_match_threshold")


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
    assert settings.book_match_threshold == 0.7
    assert settings.course_linking_enabled is True
    assert settings.course_match_threshold == 0.7
