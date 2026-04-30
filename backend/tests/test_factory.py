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
