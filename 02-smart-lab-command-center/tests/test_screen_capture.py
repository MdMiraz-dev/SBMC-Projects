"""Module: tests/test_screen_capture.py
Description: Unit tests for ScreenCaptureEngine and live screen API endpoints.
Adheres to AGENTS.md: Schema validation, image buffer integrity, and endpoint verification.
"""

import base64
import io
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from agent.screen_capture import ScreenCaptureEngine
from server.main import app, manager
from server.schemas import ClientRegistration, TelemetryPayload


@pytest.fixture
def capture_engine() -> ScreenCaptureEngine:
    return ScreenCaptureEngine(is_mock=True)


def test_generate_mock_screen_format(capture_engine: ScreenCaptureEngine):
    """Verifies that mock screen generator produces valid base64 JPEG data URI."""
    data_uri = capture_engine.generate_mock_screen(
        width=800,
        height=450,
        quality=60,
        active_title="FastAPI Development - Visual Studio Code",
        client_id="LAB-PC-01",
        student_name="Zubair Ahmed",
        is_locked=False,
    )
    assert data_uri.startswith("data:image/jpeg;base64,")

    # Verify decoding back into valid Pillow Image
    raw_b64 = data_uri.split(",", 1)[1]
    raw_bytes = base64.b64decode(raw_b64)
    img = Image.open(io.BytesIO(raw_bytes))
    assert img.format == "JPEG"
    assert img.size == (800, 450)


def test_generate_mock_screen_locked_overlay(capture_engine: ScreenCaptureEngine):
    """Verifies that locked overlay renders cleanly."""
    data_uri = capture_engine.generate_mock_screen(
        width=640,
        height=360,
        quality=50,
        client_id="LAB-PC-02",
        is_locked=True,
    )
    assert data_uri.startswith("data:image/jpeg;base64,")
    raw_bytes = base64.b64decode(data_uri.split(",", 1)[1])
    img = Image.open(io.BytesIO(raw_bytes))
    assert img.size == (640, 360)


def test_api_admin_screen_endpoint():
    """Verifies that GET /api/admin/screen/{client_id} returns workstation image."""
    with TestClient(app) as client:
        # Pre-register a workstation in manager
        engine = ScreenCaptureEngine(is_mock=True)
        sample_img = engine.generate_mock_screen(client_id="TEST-PC-99")

        # Manually register in manager for test
        from server.schemas import WorkstationState, WorkstationStatus
        manager._workstations["TEST-PC-99"] = WorkstationState(
            client_id="TEST-PC-99",
            hostname="HOST-99",
            ip_address="192.168.1.99",
            student_name="Test Student",
            status=WorkstationStatus.ONLINE,
            screen_thumbnail=sample_img,
        )

        response = client.get("/api/admin/screen/TEST-PC-99")
        assert response.status_code == 200
        data = response.json()
        assert data["client_id"] == "TEST-PC-99"
        assert data["student_name"] == "Test Student"
        assert data["image"] == sample_img


def test_api_admin_screen_not_found():
    """Negative test: Asserts 404 for unknown client ID."""
    with TestClient(app) as client:
        response = client.get("/api/admin/screen/UNKNOWN-PC-404")
        assert response.status_code == 404
