from app.llm.base import LLMProvider, LLMResponse, StreamResult


def test_llm_response_is_dataclass():
    r = LLMResponse(text="SELECT * WHERE {}", input_tokens=10, output_tokens=5)
    assert r.text == "SELECT * WHERE {}"
    assert r.input_tokens == 10
    assert r.output_tokens == 5


def test_stream_result_has_required_fields():
    sr = StreamResult(tokens=iter(["a", "b"]))
    assert list(sr.tokens) == ["a", "b"]
    assert sr.input_tokens == 0
    assert sr.output_tokens == 0


def test_stream_result_tokens_are_mutable_after_construction():
    sr = StreamResult(tokens=iter([]))
    sr.input_tokens = 42
    sr.output_tokens = 7
    assert sr.input_tokens == 42
    assert sr.output_tokens == 7


def test_llm_provider_is_protocol():
    assert hasattr(LLMProvider, "generate")
    assert hasattr(LLMProvider, "stream")
