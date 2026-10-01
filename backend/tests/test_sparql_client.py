from unittest.mock import MagicMock, patch
import pytest
from app.sparql.client import SparqlClient, SparqlResult, validate_sparql


_VALID_SPARQL = """
PREFIX evdx: <https://w3id.org/evdoxus#>
SELECT DISTINCT ?title WHERE {
  ?book a evdx:Book ;
        evdx:title ?title .
}
LIMIT 10
"""

_INVALID_SPARQL = "SELECT WHERE { broken syntax !!!"


def test_validate_sparql_returns_none_for_valid_query():
    assert validate_sparql(_VALID_SPARQL) is None


def test_validate_sparql_returns_error_string_for_invalid_query():
    error = validate_sparql(_INVALID_SPARQL)
    assert isinstance(error, str)
    assert len(error) > 0


def test_execute_returns_sparql_result():
    raw_response = {
        "head": {"vars": ["title"]},
        "results": {"bindings": [{"title": {"value": "Αλγόριθμοι"}}]},
    }
    mock_wrapper = MagicMock()
    mock_wrapper.query.return_value.convert.return_value = raw_response

    with patch("app.sparql.client.SPARQLWrapper", return_value=mock_wrapper):
        client = SparqlClient("http://example.com/sparql")
        result = client.execute(_VALID_SPARQL)

    assert isinstance(result, SparqlResult)
    assert result.columns == ["title"]
    assert result.rows == [{"title": "Αλγόριθμοι"}]


def test_execute_raises_runtime_error_on_sparql_failure():
    mock_wrapper = MagicMock()
    mock_wrapper.query.side_effect = Exception("Connection refused")

    with patch("app.sparql.client.SPARQLWrapper", return_value=mock_wrapper):
        client = SparqlClient("http://example.com/sparql")
        with pytest.raises(RuntimeError, match="SPARQL execution failed"):
            client.execute(_VALID_SPARQL)


def _execute_with_body(body):
    """Run SparqlClient.execute against a mocked GraphDB reply body."""
    mock_wrapper = MagicMock()
    mock_wrapper.query.return_value.convert.return_value = body
    with patch("app.sparql.client.SPARQLWrapper", return_value=mock_wrapper):
        return SparqlClient("http://example.com/sparql").execute("ASK { ?s ?p ?o }")


# The bodies below are exactly what GraphDB returned in the S50 probe (ADR-037):
# Content-Type application/sparql-results+json, {"head": {}, "boolean": …}.


@pytest.mark.parametrize("answer", [True, False])
def test_execute_ask_returns_one_answer_row_and_the_boolean(answer):
    """An ASK reply used to become 0 columns / 0 rows — true and false looked the same."""
    result = _execute_with_body({"head": {}, "boolean": answer})
    assert result.boolean is answer
    assert result.columns == ["answer"]
    assert result.rows == [{"answer": "true" if answer else "false"}]


def test_execute_select_has_no_boolean():
    result = _execute_with_body(
        {"head": {"vars": ["title"]}, "results": {"bindings": [{"title": {"value": "Α"}}]}}
    )
    assert result.boolean is None


def test_execute_construct_bytes_raise_a_clear_error():
    """CONSTRUCT replies with n-triples bytes (S50); before, `raw.get` raised AttributeError."""
    with pytest.raises(RuntimeError, match="only SELECT and ASK"):
        _execute_with_body(b'<https://w3id.org/evdoxus#u1> <https://w3id.org/evdoxus#name> "X" .\n')


def test_execute_unknown_json_form_raises_a_clear_error():
    with pytest.raises(RuntimeError, match="only SELECT and ASK"):
        _execute_with_body({"head": {}})


def test_execute_handles_missing_binding_columns():
    """If a binding doesn't include a variable, the value should be None."""
    raw_response = {
        "head": {"vars": ["title", "code"]},
        "results": {"bindings": [{"title": {"value": "Αλγόριθμοι"}}]},
    }
    mock_wrapper = MagicMock()
    mock_wrapper.query.return_value.convert.return_value = raw_response

    with patch("app.sparql.client.SPARQLWrapper", return_value=mock_wrapper):
        client = SparqlClient("http://example.com/sparql")
        result = client.execute(_VALID_SPARQL)

    assert result.rows[0]["code"] is None


@pytest.mark.live
def test_live_execute_returns_results():
    """Requires live GraphDB endpoint. Run with: uv run pytest -m live"""
    from app.config import settings

    client = SparqlClient(settings.graphdb_endpoint)
    result = client.execute(
        "PREFIX evdx: <https://w3id.org/evdoxus#> "
        "SELECT (COUNT(*) AS ?n) WHERE { ?s a evdx:Book } LIMIT 1"
    )
    assert result.columns == ["n"]
    assert len(result.rows) == 1
    count = int(result.rows[0]["n"])
    assert count > 0
