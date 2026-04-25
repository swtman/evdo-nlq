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
