from fastapi.testclient import TestClient

from app.config import BACKEND_DIR, Settings
from app.main import app


def test_health_ok() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["sinks"]["sns"] == "dry-run"


def test_ws_sends_snapshot_on_connect() -> None:
    with TestClient(app) as client, client.websocket_connect("/ws") as ws:
        message = ws.receive_json()
    assert message["type"] == "snapshot"
    assert "alerts" in message["data"]


def test_relative_log_path_resolves_against_backend_dir() -> None:
    settings = Settings(log_path="../data/logs/app.log")
    assert settings.resolved_log_path == (BACKEND_DIR.parent / "data/logs/app.log").resolve()
