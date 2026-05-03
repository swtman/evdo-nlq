from unittest.mock import MagicMock, patch
import pytest
from app.llm.base import LLMResponse
from app.llm.cache import DiskCache


def _make_provider(tmp_path, model="claude-haiku-4-5"):
    from app.llm.claude_provider import ClaudeProvider

    cache = DiskCache(str(tmp_path / "cache"))
    return ClaudeProvider(model=model, api_key="test-key", cache=cache)


def _mock_message(text: str, input_tokens: int = 100, output_tokens: int = 50):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    msg.usage.input_tokens = input_tokens
    msg.usage.output_tokens = output_tokens
    return msg


def test_generate_returns_llm_response(tmp_path):
    provider = _make_provider(tmp_path)
    with patch.object(provider._client.messages, "create", return_value=_mock_message("SELECT *")):
        result = provider.generate("system", "user")
    assert isinstance(result, LLMResponse)
    assert result.text == "SELECT *"
    assert result.input_tokens == 100
    assert result.output_tokens == 50


def test_generate_uses_cache_on_second_call(tmp_path):
    provider = _make_provider(tmp_path)
    with patch.object(
        provider._client.messages, "create", return_value=_mock_message("SELECT *")
    ) as mock_create:
        provider.generate("system", "user")
        provider.generate("system", "user")
    assert mock_create.call_count == 1


def test_generate_does_not_call_api_when_cache_hit(tmp_path):
    provider = _make_provider(tmp_path)
    provider._cache.set("system", "user", provider._model, "CACHED SPARQL")
    with patch.object(provider._client.messages, "create") as mock_create:
        result = provider.generate("system", "user")
    mock_create.assert_not_called()
    assert result.text == "CACHED SPARQL"


def test_stream_yields_tokens_and_sets_usage(tmp_path):
    provider = _make_provider(tmp_path)
    tokens = ["PREFIX", " evdx:", " <...>\n", "SELECT *"]

    mock_stream_ctx = MagicMock()
    mock_stream_ctx.__enter__ = MagicMock(return_value=mock_stream_ctx)
    mock_stream_ctx.__exit__ = MagicMock(return_value=False)
    mock_stream_ctx.text_stream = iter(tokens)
    mock_final = MagicMock()
    mock_final.usage.input_tokens = 80
    mock_final.usage.output_tokens = 30
    mock_stream_ctx.get_final_message.return_value = mock_final

    with patch.object(provider._client.messages, "stream", return_value=mock_stream_ctx):
        sr = provider.stream("system", "user")
        collected = list(sr.tokens)

    assert collected == tokens
    assert sr.input_tokens == 80
    assert sr.output_tokens == 30


@pytest.mark.live
def test_live_generate_returns_sparql(tmp_path):
    """Requires ANTHROPIC_API_KEY in .env. Run with: uv run pytest -m live"""
    import os
    from app.llm.claude_provider import ClaudeProvider

    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        pytest.skip("ANTHROPIC_API_KEY not set")
    cache = DiskCache(str(tmp_path / "cache"))
    provider = ClaudeProvider(model="claude-haiku-4-5", api_key=key, cache=cache)
    result = provider.generate("Respond with only: SELECT * WHERE {}", "test")
    assert "SELECT" in result.text
    assert result.input_tokens > 0
