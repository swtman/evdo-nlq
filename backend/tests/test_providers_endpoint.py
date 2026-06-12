"""Tests for GET /providers with dynamic Ollama detection."""
from unittest.mock import MagicMock, patch

import httpx
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_providers_includes_static_entries():
    with patch("app.api.providers._get_ollama_provider", return_value=None):
        resp = client.get("/providers")
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()["providers"]]
    assert "claude" in ids
    assert "gemini" in ids
    assert "fake" in ids


def test_providers_includes_ollama_when_reachable():
    from app.api.providers import ProviderInfo
    ollama_info = ProviderInfo(id="ollama", models=["qwen2.5:3b-instruct"])
    with patch("app.api.providers._get_ollama_provider", return_value=ollama_info):
        resp = client.get("/providers")
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()["providers"]]
    assert "ollama" in ids
    ollama_entry = next(p for p in resp.json()["providers"] if p["id"] == "ollama")
    assert ollama_entry["models"] == ["qwen2.5:3b-instruct"]


def test_providers_omits_ollama_when_unreachable():
    with patch("app.api.providers._get_ollama_provider", return_value=None):
        resp = client.get("/providers")
    ids = [p["id"] for p in resp.json()["providers"]]
    assert "ollama" not in ids


def test_get_ollama_provider_returns_none_on_connection_error():
    from app.api.providers import _get_ollama_provider
    with patch("httpx.get", side_effect=httpx.ConnectError("refused")):
        result = _get_ollama_provider()
    assert result is None


def test_get_ollama_provider_returns_provider_info_on_success():
    from app.api.providers import _get_ollama_provider
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {
        "models": [
            {"name": "qwen2.5:3b-instruct"},
            {"name": "qwen2.5:7b-instruct"},
        ]
    }
    with patch("httpx.get", return_value=mock_resp):
        result = _get_ollama_provider()
    assert result is not None
    assert result.id == "ollama"
    assert result.models == ["qwen2.5:3b-instruct", "qwen2.5:7b-instruct"]


def test_get_ollama_provider_returns_none_when_no_models_installed():
    from app.api.providers import _get_ollama_provider
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = {"models": []}
    with patch("httpx.get", return_value=mock_resp):
        result = _get_ollama_provider()
    assert result is None
