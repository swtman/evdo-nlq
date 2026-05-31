import pytest
from app.llm.factory import get_provider
from app.llm.fake_provider import FakeProvider
from app.llm.base import LLMProvider


def test_get_provider_fake_returns_fake_provider():
    provider = get_provider("fake", "fake-v1")
    assert isinstance(provider, FakeProvider)
    assert isinstance(provider, LLMProvider)


def test_get_provider_unknown_raises_value_error():
    with pytest.raises(ValueError, match="Unknown LLM provider"):
        get_provider("nonexistent", "model-x")


def test_get_provider_gemini_returns_gemini_provider():
    from unittest.mock import patch, MagicMock
    from app.llm.gemini_provider import GeminiProvider

    with patch("app.llm.gemini_provider.genai") as mock_genai:
        mock_genai.Client.return_value = MagicMock()
        provider = get_provider("gemini", "gemini-2.0-flash")

    assert isinstance(provider, GeminiProvider)
    assert isinstance(provider, LLMProvider)


# --- H-1: model allowlist tests ---

def test_get_provider_rejects_unknown_model_for_claude():
    """Requesting a model not in VALID_MODELS["claude"] must raise ValueError."""
    with pytest.raises(ValueError, match="not permitted"):
        get_provider("claude", "claude-opus-99")


def test_get_provider_rejects_unknown_model_for_gemini():
    with pytest.raises(ValueError, match="not permitted"):
        get_provider("gemini", "gemini-ultra-9000")


def test_get_provider_rejects_unknown_model_for_fake():
    with pytest.raises(ValueError, match="not permitted"):
        get_provider("fake", "not-a-real-fake-model")


def test_get_provider_accepts_all_listed_claude_models():
    """Every model in VALID_MODELS["claude"] must NOT raise on validation."""
    from app.llm.factory import VALID_MODELS
    from unittest.mock import patch, MagicMock

    for model in VALID_MODELS["claude"]:
        with patch("app.llm.claude_provider.anthropic") as mock_anthropic:
            mock_anthropic.Anthropic.return_value = MagicMock()
            # Should not raise ValueError for any listed model
            provider = get_provider("claude", model)
            assert provider is not None


def test_get_provider_ollama_skips_allowlist_check():
    """Ollama is excluded from the allowlist — arbitrary model strings are allowed."""
    from unittest.mock import patch, MagicMock
    # Should not raise, even with a non-standard model name
    with patch("app.llm.ollama_provider.httpx") as mock_httpx:
        mock_httpx.Client.return_value = MagicMock()
        provider = get_provider("ollama", "llama3:latest")
        assert provider is not None
