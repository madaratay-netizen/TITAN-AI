"""API integration tests using FastAPI's TestClient against the real engine.

These hit the actual hardware detector, so they assert structure/behaviour
rather than specific values. The chat endpoint is NOT called here (it needs a
running model); it is exercised separately by scripts/offline_test.py.
"""
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402
from backend.app.main import app            # noqa: E402

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["offline_mode"] is True


def test_hardware_shape():
    r = client.get("/api/hardware")
    assert r.status_code == 200
    hw = r.json()
    assert "cpu" in hw and "memory" in hw and "disks" in hw
    assert hw["cpu"]["logical_cores"] >= 1
    assert hw["memory"]["total_gb"] > 0


def test_profile_has_key():
    r = client.get("/api/profile")
    assert r.status_code == 200
    assert r.json()["profile"]["key"] in {"P1", "P2", "P3", "P4", "P5"}


def test_models_endpoint():
    r = client.get("/api/models")
    assert r.status_code == 200
    body = r.json()
    assert any(m["name"] == "qwen3.5:4b" for m in body["models"])
    for m in body["models"]:
        assert m["compatibility_status"] in {"ok", "cpu_only", "incompatible"}


def test_offline_endpoint_reports_level():
    r = client.get("/api/offline")
    assert r.status_code == 200
    assert r.json()["isolation_level"] in {
        "no_internet_requirement", "no_network_connectivity", "fully_isolated"}


def test_chat_rejects_when_configured_nonlocal(monkeypatch):
    # Offline guard: a non-loopback AI host must be refused.
    from backend.app import main
    monkeypatch.setattr(main.settings, "ollama_host", "http://example.com:11434")
    r = client.post("/api/chat", json={"prompt": "hi"})
    assert r.status_code == 400
