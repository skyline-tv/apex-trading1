import os
import sys
from pathlib import Path

from fastapi.testclient import TestClient


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import app as app_module  # noqa: E402


def test_root_endpoint():
    client = TestClient(app_module.app)
    response = client.get("/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"


def test_healthz_endpoint():
    client = TestClient(app_module.app)
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readyz_returns_503_without_openai_key():
    original_key = app_module.OPENAI_API_KEY
    app_module.OPENAI_API_KEY = ""
    try:
        client = TestClient(app_module.app)
        response = client.get("/readyz")
    finally:
        app_module.OPENAI_API_KEY = original_key
    assert response.status_code == 503
    payload = response.json()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["database_available"] is True
    assert payload["checks"]["openai_api_key_configured"] is False


def test_readyz_returns_200_with_openai_key():
    original_key = app_module.OPENAI_API_KEY
    app_module.OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "dummy_key")
    try:
        client = TestClient(app_module.app)
        response = client.get("/readyz")
    finally:
        app_module.OPENAI_API_KEY = original_key
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["database_available"] is True
    assert payload["checks"]["openai_api_key_configured"] is True


def test_performance_report_endpoint():
    client = TestClient(app_module.app)
    response = client.get("/performance/report?limit=100")
    assert response.status_code == 200
    payload = response.json()
    assert "window_trades" in payload
    assert "win_rate" in payload
    assert "expectancy_per_trade" in payload
    assert "daily_realized_last_7d" in payload
    assert isinstance(payload["daily_realized_last_7d"], list)
