"""Module: tests/test_integration.py
Description: End-to-end HTTP and FastAPI API integration tests for Central Server.
Adheres to AGENTS.md: REST endpoint verification and payload validation.
"""

import pytest
from fastapi.testclient import TestClient
from server.main import app


@pytest.fixture
def client():
    # Use context manager to trigger lifespan cleanly or plain client
    with TestClient(app) as test_client:
        yield test_client


def test_dashboard_page_loads(client: TestClient):
    """Verifies that instructor command dashboard HTML renders cleanly."""
    response = client.get("/")
    assert response.status_code == 200
    assert "Smart Lab Command Center" in response.text
    assert "As-Sunnah Lab Edition" in response.text
    assert "Workstations Grid Overview" in response.text


def test_api_admin_workstations_list(client: TestClient):
    """Verifies GET /api/admin/workstations returns a valid JSON array."""
    response = client.get("/api/admin/workstations")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_api_curfew_status_and_override(client: TestClient):
    """Verifies curfew status inspection and instructor override toggling."""
    resp_status = client.get("/api/admin/curfew/status")
    assert resp_status.status_code == 200
    data = resp_status.json()
    assert "config" in data
    assert "current_stage" in data

    # Toggle override ON
    resp_override = client.post(
        "/api/admin/curfew/override",
        json={"active": True, "reason": "Integration Test Exam"},
    )
    assert resp_override.status_code == 200
    assert resp_override.json()["override_active"] is True

    # Re-verify status reflects override
    resp_status_after = client.get("/api/admin/curfew/status")
    assert resp_status_after.json()["current_stage"] == "OVERRIDE"

    # Reset override OFF
    client.post("/api/admin/curfew/override", json={"active": False})


def test_api_command_broadcast_endpoint(client: TestClient):
    """Verifies master broadcast API endpoint accepts typed commands."""
    response = client.post(
        "/api/admin/command/broadcast",
        json={"command": "BROADCAST_MESSAGE", "message": "Automated system test."},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data["command"] == "BROADCAST_MESSAGE"


def test_api_audit_log_endpoint(client: TestClient):
    """Verifies GET /api/admin/audit-log returns a valid JSON list."""
    response = client.get("/api/admin/audit-log")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


def test_api_screen_not_found(client: TestClient):
    """Verifies GET /api/admin/screen/{client_id} returns 404 for unknown client."""
    response = client.get("/api/admin/screen/NON-EXISTENT-PC")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()

