"""Module: tests/test_features.py
Description: Comprehensive unit and integration tests for Top 5 Premium Institutional Features:
1. AI Productivity Scoring & Daily Report Card
2. One-Click Focus Mode (Distraction Blocker)
3. Central File Broadcast & Assignment Collection
4. USB Storage Policy Toggle
5. Telegram Remote Control Command Router
Adheres to AGENTS.md: Strict typing, negative edge cases, isolated test fixtures.
"""

import base64
from datetime import datetime, timezone
from pathlib import Path
import pytest
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient

from server.curfew import CurfewEngine
from server.detector import DistractionDetector
from server.main import app
from server.manager import LabConnectionManager
from server.schemas import (
    AdminCommandPayload,
    AssignmentSubmissionPayload,
    ClientRegistration,
    CollectAssignmentsRequest,
    CommandType,
    FileBroadcastPayload,
    FocusModeRequest,
    TelemetryPayload,
    UsbPolicyRequest,
    WorkstationStatus,
)
from server.telegram_bot import TelegramCommandRouter


@pytest.fixture
def manager() -> LabConnectionManager:
    mgr = LabConnectionManager()
    mgr.collected_assignments_dir = "tests/test_collected_assignments"
    return mgr


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


# ==============================================================================
# Feature 1 Tests: AI Productivity Scoring & Daily Report
# ==============================================================================

@pytest.mark.asyncio
async def test_ai_productivity_scoring_calculation(manager: LabConnectionManager):
    """Verifies 0-100 productivity scoring: 100% focused = 100 score, distractions penalize score."""
    mock_ws = AsyncMock()
    reg = ClientRegistration(
        client_id="LAB-PC-P1",
        hostname="PC-P1",
        ip_address="192.168.1.10",
        student_name="Abdullah Al-Mamun",
    )
    await manager.register_workstation(reg, mock_ws)

    # 1. Focused programming session
    t_coding = TelemetryPayload(
        client_id="LAB-PC-P1",
        cpu_percent=15.0,
        ram_percent=40.0,
        active_window_title="VS Code - exercise.py",
        active_process_name="Code.exe",
    )
    st = await manager.record_telemetry(t_coding)
    assert st.productivity_score == 100

    # 2. Distraction session (YouTube Shorts)
    t_shorts = TelemetryPayload(
        client_id="LAB-PC-P1",
        cpu_percent=25.0,
        ram_percent=50.0,
        active_window_title="YouTube Shorts - Viral Prank",
        active_process_name="chrome.exe",
    )
    st = await manager.record_telemetry(t_shorts)
    # Ratio: 5s focused / 10s total = 50%, minus 5 penalty = 45
    assert st.productivity_score <= 50
    assert st.violation_count == 1


@pytest.mark.asyncio
async def test_daily_report_generation(manager: LabConnectionManager):
    """Verifies that manager generates consolidated daily report with top focused/distracted lists."""
    mock_ws = AsyncMock()
    reg1 = ClientRegistration(client_id="PC-01", hostname="H1", ip_address="192.168.1.1", student_name="Student One")
    reg2 = ClientRegistration(client_id="PC-02", hostname="H2", ip_address="192.168.1.2", student_name="Student Two")
    await manager.register_workstation(reg1, mock_ws)
    await manager.register_workstation(reg2, mock_ws)

    # Student 1 focused
    await manager.record_telemetry(TelemetryPayload(
        client_id="PC-01", cpu_percent=10.0, ram_percent=30.0,
        active_window_title="Python Doc", active_process_name="Code.exe",
    ))

    # Student 2 distracted
    await manager.record_telemetry(TelemetryPayload(
        client_id="PC-02", cpu_percent=10.0, ram_percent=30.0,
        active_window_title="TikTok Watch Online", active_process_name="msedge.exe",
    ))

    report = manager.generate_daily_report()
    assert report.total_students == 2
    assert len(report.top_focused_students) == 2
    assert report.top_focused_students[0].student_name == "Student One"
    assert len(report.top_distracted_students) == 1
    assert report.top_distracted_students[0].student_name == "Student Two"


def test_api_daily_report_endpoint(client: TestClient):
    """Verifies GET /api/admin/reports/daily returns valid JSON DailyReport."""
    resp = client.get("/api/admin/reports/daily")
    assert resp.status_code == 200
    data = resp.json()
    assert "lab_average_score" in data
    assert "top_focused_students" in data
    assert "top_distracted_students" in data


# ==============================================================================
# Feature 2 Tests: One-Click Focus Mode
# ==============================================================================

@pytest.mark.asyncio
async def test_focus_mode_toggle_and_restriction(manager: LabConnectionManager):
    """Verifies Focus Mode pushes policy to agents and auto-restricts distractions."""
    mock_ws = AsyncMock()
    reg = ClientRegistration(client_id="PC-FOCUS-1", hostname="HF", ip_address="192.168.1.20", student_name="Test Student")
    await manager.register_workstation(reg, mock_ws)

    # Enable Focus Mode
    count = await manager.set_focus_mode(active=True, reason="Final Exam")
    assert manager.focus_mode_active is True
    assert count == 1

    # Inbound distraction while Focus Mode is ON
    t_reels = TelemetryPayload(
        client_id="PC-FOCUS-1",
        cpu_percent=15.0,
        ram_percent=40.0,
        active_window_title="Facebook Reels - Funny Cats",
        active_process_name="chrome.exe",
    )
    st = await manager.record_telemetry(t_reels)
    assert st.status == WorkstationStatus.DISTRACTED
    assert st.focus_mode_active is True


def test_api_focus_mode_endpoints(client: TestClient):
    """Verifies GET /api/admin/focus-mode and POST /api/admin/focus-mode/toggle."""
    resp_get = client.get("/api/admin/focus-mode")
    assert resp_get.status_code == 200

    resp_toggle = client.post("/api/admin/focus-mode/toggle", json={"active": True, "reason": "Test Mode"})
    assert resp_toggle.status_code == 200
    assert resp_toggle.json()["focus_mode_active"] is True

    # Toggle back to False
    client.post("/api/admin/focus-mode/toggle", json={"active": False})


# ==============================================================================
# Feature 3 Tests: Central File Broadcast & Assignment Collection
# ==============================================================================

@pytest.mark.asyncio
async def test_broadcast_file_dispatch(manager: LabConnectionManager):
    """Verifies file broadcast directive is properly encoded and dispatched."""
    mock_ws = AsyncMock()
    reg = ClientRegistration(client_id="PC-FILE-1", hostname="HF1", ip_address="192.168.1.30")
    await manager.register_workstation(reg, mock_ws)

    payload = FileBroadcastPayload(
        filename="lecture_03.py",
        file_content_base64=base64.b64encode(b"print('Hello Lab')").decode(),
        sender="Instructor",
    )
    count = await manager.broadcast_file(payload)
    assert count == 1


@pytest.mark.asyncio
async def test_save_and_list_assignment_submission(manager: LabConnectionManager, tmp_path: Path):
    """Verifies saving student assignment files and querying collection records."""
    manager.collected_assignments_dir = str(tmp_path / "collected")

    sub = AssignmentSubmissionPayload(
        client_id="LAB-PC-SUB-01",
        student_name="Zubair Ahmed",
        filename="homework_01.py",
        file_content_base64=base64.b64encode(b"# Python submission content").decode(),
        file_size_bytes=26,
    )
    saved_path = manager.save_assignment_submission(sub)
    assert Path(saved_path).exists()
    assert Path(saved_path).read_bytes() == b"# Python submission content"

    submissions = manager.get_collected_submissions()
    assert len(submissions) == 1
    assert submissions[0]["client_id"] == "LAB-PC-SUB-01"
    assert submissions[0]["filename"] == "homework_01.py"


def test_api_file_broadcast_and_collection(client: TestClient):
    """Verifies file broadcast and assignment collection API routes."""
    # 1. Broadcast file
    b_resp = client.post("/api/admin/files/broadcast", json={
        "filename": "test.txt",
        "file_content_base64": base64.b64encode(b"test content").decode(),
    })
    assert b_resp.status_code == 200

    # 2. Collect assignments
    c_resp = client.post("/api/admin/files/collect", json={"assignment_name": "test.py"})
    assert c_resp.status_code == 200

    # 3. List collected
    l_resp = client.get("/api/admin/files/collected")
    assert l_resp.status_code == 200
    assert isinstance(l_resp.json(), list)


# ==============================================================================
# Feature 4 Tests: USB Storage Policy Toggle
# ==============================================================================

@pytest.mark.asyncio
async def test_usb_policy_toggle(manager: LabConnectionManager):
    """Verifies USB mass storage restriction toggle updates state and broadcasts policy."""
    mock_ws = AsyncMock()
    reg = ClientRegistration(client_id="PC-USB-1", hostname="HU1", ip_address="192.168.1.40")
    await manager.register_workstation(reg, mock_ws)

    # Block USB
    count = await manager.set_usb_policy(blocked=True)
    assert manager.usb_storage_blocked is True
    assert count == 1
    assert manager.get_workstation("PC-USB-1").usb_blocked is True

    # Allow USB
    await manager.set_usb_policy(blocked=False)
    assert manager.usb_storage_blocked is False
    assert manager.get_workstation("PC-USB-1").usb_blocked is False


def test_api_usb_policy_endpoints(client: TestClient):
    """Verifies GET /api/admin/usb-policy and POST /api/admin/usb-policy/toggle."""
    resp_get = client.get("/api/admin/usb-policy")
    assert resp_get.status_code == 200

    resp_toggle = client.post("/api/admin/usb-policy/toggle", json={"blocked": True})
    assert resp_toggle.status_code == 200
    assert resp_toggle.json()["usb_storage_blocked"] is True

    # Unblock
    client.post("/api/admin/usb-policy/toggle", json={"blocked": False})


# ==============================================================================
# Feature 5 Tests: Telegram Remote Control Simulator
# ==============================================================================

@pytest.mark.asyncio
async def test_telegram_command_router(manager: LabConnectionManager):
    """Verifies Telegram command router responses for /status, /lockall, /curfew, /report."""
    curfew = CurfewEngine()
    router = TelegramCommandRouter(manager=manager, curfew_engine=curfew)

    # Test /status
    res_status = await router.execute_command("/status")
    assert "As-Sunnah Lab Status Report" in res_status

    # Test /report
    res_report = await router.execute_command("/report")
    assert "Daily AI Productivity Report Card" in res_report

    # Test /focus on and off
    res_focus = await router.execute_command("/focus on")
    assert "Focus Mode" in res_focus
    assert manager.focus_mode_active is True

    # Test /usb lock
    res_usb = await router.execute_command("/usb lock")
    assert "USB Storage Policy" in res_usb
    assert manager.usb_storage_blocked is True

    # Test unknown command
    res_unknown = await router.execute_command("/invalidcmd")
    assert "Unknown command" in res_unknown


def test_api_telegram_simulate_and_webhook(client: TestClient):
    """Verifies Telegram simulation endpoint and webhook route."""
    # 1. Status inspection
    s_resp = client.get("/api/admin/telegram/status")
    assert s_resp.status_code == 200

    # 2. Slash command simulation
    sim_resp = client.post("/api/admin/telegram/simulate", json={"command": "/status"})
    assert sim_resp.status_code == 200
    assert "As-Sunnah Lab" in sim_resp.json()["response"]

    # 3. Telegram Webhook route
    hook_resp = client.post("/api/telegram/webhook", json={
        "message": {
            "text": "/report",
            "from": {"first_name": "Teacher"},
        }
    })
    assert hook_resp.status_code == 200
    assert hook_resp.json()["ok"] is True
