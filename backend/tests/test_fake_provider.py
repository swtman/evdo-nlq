from app.llm.fake_provider import FakeProvider
from app.llm.base import LLMResponse, LLMProvider


_SYSTEM = "You are a SPARQL generator."
_USER = "List all books."


def test_generate_returns_llm_response():
    provider = FakeProvider()
    result = provider.generate(_SYSTEM, _USER)
    assert isinstance(result, LLMResponse)
    assert "PREFIX evdx:" in result.text
    assert "SELECT" in result.text
    assert result.input_tokens >= 0
    assert result.output_tokens >= 0


def test_stream_yields_characters_that_assemble_to_generate_output():
    provider = FakeProvider()
    streamed = "".join(provider.stream(_SYSTEM, _USER))
    expected = provider.generate(_SYSTEM, _USER).text
    assert streamed == expected


def test_fake_provider_satisfies_protocol():
    provider = FakeProvider()
    assert isinstance(provider, LLMProvider)
