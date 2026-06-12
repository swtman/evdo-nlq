from app.config import settings


def test_settings_has_required_fields():
    assert hasattr(settings, "llm_provider")
    assert hasattr(settings, "llm_model")
    assert hasattr(settings, "graphdb_endpoint")
    assert hasattr(settings, "llm_cache_dir")
    assert hasattr(settings, "llm_cache_disabled")
    assert hasattr(settings, "frontend_origin")
    assert hasattr(settings, "log_level")


def test_settings_defaults():
    assert settings.llm_provider == "claude"
    assert settings.llm_model == "claude-haiku-4-5"
    assert "EvdoGraph" in settings.graphdb_endpoint
    assert settings.llm_cache_dir == ".llm_cache"
    assert settings.llm_cache_disabled is False
