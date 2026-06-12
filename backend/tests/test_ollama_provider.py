"""
Unit tests for OllamaProvider.

All tests mock httpx — no real Ollama server needed.
The mock shapes follow Ollama's actual API response format:
  - Non-streaming POST /api/generate → {"response": "...", "done": true, "eval_count": N, "prompt_eval_count": M}
  - Streaming POST /api/generate    → ndjson lines, last line has "done": true with eval counts
"""
import json
from unittest.mock import MagicMock, patch


from app.llm.base import LLMResponse
from app.llm.cache import DiskCache


def _make_provider(tmp_path, model="qwen2.5:3b-instruct"):
    from app.llm.ollama_provider import OllamaProvider

    cache = DiskCache(str(tmp_path / "cache"))
    return OllamaProvider(
        model=model,
        base_url="http://localhost:11434",
        cache=cache,
    )


def _mock_generate_response(text: str, prompt_eval_count: int = 100, eval_count: int = 50):
    """Build a mock httpx.Response for a non-streaming /api/generate call."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "model": "qwen2.5:3b-instruct",
        "response": text,
        "done": True,
        "prompt_eval_count": prompt_eval_count,
        "eval_count": eval_count,
    }
    return resp


def _mock_stream_lines(tokens: list[str], prompt_eval_count: int = 80, eval_count: int = 30):
    """Build ndjson lines as Ollama would stream them."""
    lines = [
        json.dumps({"response": t, "done": False})
        for t in tokens
    ]
    lines.append(json.dumps({
        "response": "",
        "done": True,
        "prompt_eval_count": prompt_eval_count,
        "eval_count": eval_count,
    }))
    return lines


# ---------------------------------------------------------------------------
# generate() tests
# ---------------------------------------------------------------------------

def test_generate_returns_llm_response(tmp_path):
    provider = _make_provider(tmp_path)
    mock_resp = _mock_generate_response("SELECT * WHERE { ?s ?p ?o }")

    with patch("httpx.post", return_value=mock_resp):
        result = provider.generate("system prompt", "user question")

    assert isinstance(result, LLMResponse)
    assert result.text == "SELECT * WHERE { ?s ?p ?o }"
    assert result.input_tokens == 100
    assert result.output_tokens == 50


def test_generate_uses_cache_on_second_call(tmp_path):
    provider = _make_provider(tmp_path)
    mock_resp = _mock_generate_response("SELECT *")

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        provider.generate("system", "user")
        provider.generate("system", "user")

    assert mock_post.call_count == 1


def test_generate_does_not_call_api_when_cache_hit(tmp_path):
    provider = _make_provider(tmp_path)
    provider._cache.set("system", "user", provider._model, "CACHED SPARQL")

    with patch("httpx.post") as mock_post:
        result = provider.generate("system", "user")

    mock_post.assert_not_called()
    assert result.text == "CACHED SPARQL"
    assert result.input_tokens == 0
    assert result.output_tokens == 0


def test_generate_passes_system_and_prompt_separately(tmp_path):
    """Verify generate() sends system and prompt as separate JSON fields."""
    provider = _make_provider(tmp_path)
    mock_resp = _mock_generate_response("SELECT *")

    with patch("httpx.post", return_value=mock_resp) as mock_post:
        provider.generate("my system prompt", "my user question")

    call_kwargs = mock_post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
    assert payload["system"] == "my system prompt"
    assert payload["prompt"] == "my user question"
    assert payload["stream"] is False


# ---------------------------------------------------------------------------
# stream() tests
# ---------------------------------------------------------------------------

def test_stream_yields_tokens_and_sets_usage(tmp_path):
    provider = _make_provider(tmp_path)
    tokens = ["PREFIX", " evdx:", " <...>\n", "SELECT *"]
    lines = _mock_stream_lines(tokens, prompt_eval_count=80, eval_count=30)

    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.iter_lines = MagicMock(return_value=iter(lines))

    with patch("httpx.stream", return_value=mock_resp):
        sr = provider.stream("system", "user")
        collected = list(sr.tokens)

    assert collected == tokens
    assert sr.input_tokens == 80
    assert sr.output_tokens == 30


def test_stream_uses_cache_on_hit(tmp_path):
    provider = _make_provider(tmp_path)
    provider._cache.set("system", "user", provider._model, "CACHED SPARQL")

    with patch("httpx.stream") as mock_stream:
        sr = provider.stream("system", "user")
        collected = list(sr.tokens)

    mock_stream.assert_not_called()
    assert "".join(collected) == "CACHED SPARQL"


def test_stream_writes_to_cache_after_exhaustion(tmp_path):
    provider = _make_provider(tmp_path)
    tokens = ["SELECT", " *"]
    lines = _mock_stream_lines(tokens)

    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.iter_lines = MagicMock(return_value=iter(lines))

    with patch("httpx.stream", return_value=mock_resp):
        sr = provider.stream("system", "user")
        list(sr.tokens)  # exhaust

    cached = provider._cache.get("system", "user", provider._model)
    assert cached == "SELECT *"


def test_provider_satisfies_protocol(tmp_path):
    """Runtime isinstance check via @runtime_checkable."""
    from app.llm.base import LLMProvider
    provider = _make_provider(tmp_path)
    assert isinstance(provider, LLMProvider)
