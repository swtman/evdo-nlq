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


def test_stream_yields_tokens_and_sets_usage(tmp_path):
    provider = _make_provider(tmp_path)

    def _make_chunk(text, prompt_tokens=None, candidate_tokens=None):
        chunk = MagicMock()
        chunk.text = text
        if prompt_tokens is not None:
            chunk.usage_metadata = MagicMock()
            chunk.usage_metadata.prompt_token_count = prompt_tokens
            chunk.usage_metadata.candidates_token_count = candidate_tokens
        else:
            chunk.usage_metadata = None
        return chunk

    chunks = [
        _make_chunk("PREFIX"),
        _make_chunk(" evdx:"),
        _make_chunk("SELECT *", prompt_tokens=80, candidate_tokens=30),
    ]

    with patch.object(
        provider._client.models,
        "generate_content_stream",
        return_value=iter(chunks),
    ):
        result = list(provider.stream("system", "user"))

    assert result == ["PREFIX", " evdx:", "SELECT *"]
    assert provider.last_input_tokens == 80
    assert provider.last_output_tokens == 30
    assert provider._cache.get("system", "user", provider._model) == "PREFIX evdx:SELECT *"


def test_stream_uses_cache_on_second_call(tmp_path):
    provider = _make_provider(tmp_path)
    provider._cache.set("system", "user", provider._model, "CACHED SPARQL")
    with patch.object(provider._client.models, "generate_content_stream") as mock_stream:
        result = list(provider.stream("system", "user"))
    mock_stream.assert_not_called()
    assert result == ["CACHED SPARQL"]


@pytest.mark.live
def test_live_generate_returns_sparql(tmp_path):
    """Requires GEMINI_API_KEY in .env. Run with: uv run pytest -m live"""
    import os
    from app.llm.gemini_provider import GeminiProvider

    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        pytest.skip("GEMINI_API_KEY not set")
    cache = DiskCache(str(tmp_path / "cache"))
    provider = GeminiProvider(model="gemini-2.0-flash", api_key=key, cache=cache)
    result = provider.generate("Respond with only: SELECT * WHERE {}", "test")
    assert "SELECT" in result.text
    assert result.input_tokens > 0
