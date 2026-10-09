"""Module: tests/test_voice_and_host.py
Description: Automated test suite for Telegram AI Bengali Voice Recognition and Master Host Workstation Control.
Adheres to AGENTS.md: Rigorous unit & integration tests, edge cases, negative tests, schema contracts.
"""

import base64
import pytest
from fastapi.testclient import TestClient

from server.main import app, manager, telegram_router
from server.schemas import WorkstationStatus, WorkstationState
from server.voice_ai import VoiceCommandAI


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def voice_ai():
    return VoiceCommandAI()


# ==============================================================================
# Feature 6: Master Host Workstation Control Tests
# ==============================================================================

def test_master_host_registration_and_metrics():
    """Verifies that update_host_metrics correctly populates MASTER-ADMIN-PC."""
    host_state = manager.update_host_metrics()
    assert host_state.client_id == manager.MASTER_HOST_ID
    assert host_state.is_master_host is True
    assert host_state.latest_telemetry is not None
    assert 0.0 <= host_state.latest_telemetry.cpu_percent <= 100.0
    assert 0.0 <= host_state.latest_telemetry.ram_percent <= 100.0


def test_master_host_prioritized_sorting():
    """Verifies that MASTER-ADMIN-PC is always the first item in get_all_workstations."""
    manager.update_host_metrics()
    # Add a dummy workstation with an alphabetical ID that would otherwise come before 'M'
    manager._workstations["AAA-PC-99"] = WorkstationState(
        client_id="AAA-PC-99",
        hostname="HOST-AAA",
        ip_address="192.168.1.99",
        student_name="Early Alphabet Student",
    )
    all_pcs = manager.get_all_workstations()
    assert len(all_pcs) >= 2
    assert all_pcs[0].client_id == manager.MASTER_HOST_ID
    assert all_pcs[0].is_master_host is True


@pytest.mark.asyncio
async def test_master_host_lock_unlock_sleep():
    """Tests host lock, unlock, and sleep lifecycle transitions."""
    # Lock host
    lock_res = await manager.lock_host_machine(reason="Test suite lock")
    assert lock_res["status"] == "success"
    assert lock_res["is_locked"] is True
    host = manager.get_workstation(manager.MASTER_HOST_ID)
    assert host.curfew_locked is True
    assert host.status == WorkstationStatus.CURFEW_LOCKED

    # Unlock host
    unlock_res = await manager.unlock_host_machine(reason="Test suite unlock")
    assert unlock_res["status"] == "success"
    assert unlock_res["is_locked"] is False
    assert host.curfew_locked is False
    assert host.status == WorkstationStatus.ONLINE

    # Sleep host
    sleep_res = await manager.sleep_host_machine(reason="Test suite sleep")
    assert sleep_res["status"] == "success"
    assert host.status == WorkstationStatus.IDLE


def test_api_host_endpoints(client):
    """Verifies REST endpoints for Master Host metrics and power actions."""
    # GET metrics
    res_metrics = client.get("/api/admin/host/metrics")
    assert res_metrics.status_code == 200
    data = res_metrics.json()
    assert data["client_id"] == "MASTER-ADMIN-PC"
    assert data["is_master_host"] is True

    # POST lock
    res_lock = client.post("/api/admin/host/lock", json={"action": "LOCK", "reason": "API Test"})
    assert res_lock.status_code == 200
    assert res_lock.json()["is_locked"] is True

    # POST unlock
    res_unlock = client.post("/api/admin/host/unlock", json={"action": "UNLOCK", "reason": "API Test"})
    assert res_unlock.status_code == 200
    assert res_unlock.json()["is_locked"] is False

    # POST sleep
    res_sleep = client.post("/api/admin/host/sleep", json={"action": "SLEEP", "reason": "API Test"})
    assert res_sleep.status_code == 200
    assert res_sleep.json()["action"] == "SLEEP_HOST"


# ==============================================================================
# Feature 7: Telegram AI Bengali Voice Recognition Tests
# ==============================================================================

@pytest.mark.parametrize(
    "bengali_utterance,expected_command",
    [
        ("ল্যাব লক করো", "/lockall"),
        ("সব পিসি লক করো", "/lockall"),
        ("পিসিগুলো লক করুন", "/lockall"),
        ("সবাইকে আনলক করো", "/unlockall"),
        ("ল্যাব আনলক করুন", "/unlockall"),
        ("ল্যাব স্ট্যাটাস বলো", "/status"),
        ("ল্যাবের অবস্থা কি", "/status"),
        ("কার্ফিউ চালু করো", "/curfew toggle"),
        ("কার্ফিউ টগল করো", "/curfew toggle"),
        ("ফোকাস মোড অন করো", "/focus on"),
        ("ফোকাস মোড চালু করো", "/focus on"),
        ("ফোকাস মোড বন্ধ করো", "/focus off"),
        ("ফোকাস অফ করো", "/focus off"),
        ("ইউএসবি ব্লক করো", "/usb lock"),
        ("ইউএসবি লক করো", "/usb lock"),
        ("ইউএসবি আনলক করো", "/usb unlock"),
        ("ইউএসবি চালু করো", "/usb unlock"),
        ("আজকের রিপোর্ট দাও", "/report"),
        ("রিপোর্ট দেখাও", "/report"),
        ("ল্যাব শাটডাউন করো", "/shutdownall"),
        ("সব পিসি বন্ধ করো", "/shutdownall"),
        ("হোস্ট পিসি লক করো", "/host lock"),
        ("মাস্টার পিসি আনলক করো", "/host unlock"),
        ("হোস্ট স্লিপ করো", "/host sleep"),
    ],
)
def test_bengali_nlp_voice_intent_mapping(voice_ai, bengali_utterance, expected_command):
    """Verifies that Bengali voice phrases map with 100% precision to the correct slash commands."""
    cmd = voice_ai.map_bengali_text_to_command(bengali_utterance)
    assert cmd == expected_command


@pytest.mark.asyncio
async def test_telegram_router_voice_handler():
    """Verifies end-to-end handle_voice_message executing voice directives."""
    voice_res = await telegram_router.handle_voice_message(
        spoken_text="ল্যাব স্ট্যাটাস বলো",
        sender="Dr. Tareq",
    )
    assert voice_res["success"] is True
    assert voice_res["transcript"] == "ল্যাব স্ট্যাটাস বলো"
    assert voice_res["resolved_command"] == "/status"
    assert "As-Sunnah Lab Status Report" in voice_res["reply_message"]
    assert "Dr. Tareq" in voice_res["execution_result"] or "Registered PCs" in voice_res["reply_message"]


def test_api_telegram_voice_simulate(client):
    """Verifies the /api/admin/telegram/voice-simulate endpoint."""
    payload = {
        "spoken_text": "ল্যাব লক করো",
        "sender": "Web Voice Console",
    }
    res = client.post("/api/admin/telegram/voice-simulate", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["transcript"] == "ল্যাব লক করো"
    assert data["resolved_command"] == "/lockall"
    assert "Lock Dispatched" in data["reply_message"]


def test_api_telegram_webhook_voice_note(client):
    """Verifies official webhook handling when a voice note payload is received."""
    webhook_payload = {
        "message": {
            "from": {"first_name": "Ustadh Zubair"},
            "voice": {
                "file_id": "mock_voice_file_id_123",
                "duration": 3,
                "mime_type": "audio/ogg",
            },
        }
    }
    res = client.post("/api/telegram/webhook", json=webhook_payload)
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["type"] == "voice"
    assert "ভয়েস কমান্ড শনাক্ত হয়েছে" in data["reply"]
