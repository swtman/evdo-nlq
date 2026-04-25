from app.llm.base import LLMResponse, LLMProvider


def test_llm_response_is_dataclass():
    r = LLMResponse(text="SELECT * WHERE {}", input_tokens=10, output_tokens=5)
    assert r.text == "SELECT * WHERE {}"
    assert r.input_tokens == 10
    assert r.output_tokens == 5


def test_llm_provider_is_protocol():
    assert hasattr(LLMProvider, "generate")
    assert hasattr(LLMProvider, "stream")
