from unittest.mock import MagicMock, patch

import pytest

from app.llm.base import LLMResponse
from app.llm.cache import DiskCache


def _make_provider(tmp_path, model="gemini-2.0-flash"):
    from app.llm.gemini_provider import GeminiProvider

    cache = DiskCache(str(tmp_path / "cache"))
    return GeminiProvider(model=model, api_key="test-key", cache=cache)


def _mock_response(text: str, input_tokens: int = 100, output_tokens: int = 50):
    resp = MagicMock()
    resp.text = text
    resp.usage_metadata.prompt_token_count = input_tokens
    resp.usage_metadata.candidates_token_count = output_tokens
    return resp


def test_generate_returns_llm_response(tmp_path):
    provider = _make_provider(tmp_path)
    with patch.object(
        provider._client.models, "generate_content", return_value=_mock_response("SELECT *")
    ):
        result = provider.generate("system", "user")
    assert isinstance(result, LLMResponse)
    assert result.text == "SELECT *"
    assert result.input_tokens == 100
    assert result.output_tokens == 50


def test_generate_uses_cache_on_second_call(tmp_path):
    provider = _make_provider(tmp_path)
    with patch.object(
        provider._client.models,
        "generate_content",
        return_value=_mock_response("SELECT *"),
    ) as mock_generate:
        provider.generate("system", "user")
        provider.generate("system", "user")
    assert mock_generate.call_count == 1


def test_generate_does_not_call_api_when_cache_hit(tmp_path):
    provider = _make_provider(tmp_path)
    provider._cache.set("system", "user", provider._model, "CACHED SPARQL")
    with patch.object(provider._client.models, "generate_content") as mock_generate:
        result = provider.generate("system", "user")
    mock_generate.assert_not_called()
    assert result.text == "CACHED SPARQL"
