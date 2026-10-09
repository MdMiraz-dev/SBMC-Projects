"""Module: tests/test_manager.py
Description: Unit tests for LabConnectionManager and Heartbeat Tamper Watchdog.
Adheres to AGENTS.md: Asynchronous tests, state transition verification.
"""

from datetime import datetime, timedelta, timezone
import pytest
from unittest.mock import AsyncMock

from server.detector import DistractionDetector
from server.manager import LabConnectionManager
from server.schemas import (
    AdminCommandPayload,
    ClientRegistration,
    CommandType,
    TelemetryPayload,
    WorkstationStatus,
)


@pytest.fixture
def manager() -> LabConnectionManager:
    return LabConnectionManager()


@pytest.mark.asyncio
async def test_register_workstation(manager: LabConnectionManager):
    """Verifies workstation registration and socket tracking."""
    mock_ws = AsyncMock()
    reg = ClientRegistration(
        client_id="LAB-PC-01",
        hostname="PC-01",
        ip_address="192.168.1.50",
        student_name="Tariqul Islam",
    )
    state = await manager.register_workstation(reg, mock_ws)
    assert state.client_id == "LAB-PC-01"
    assert state.status == WorkstationStatus.ONLINE
    assert len(manager.get_all_workstations()) == 1


@pytest.mark.asyncio
async def test_telemetry_triggers_distraction_status(manager: LabConnectionManager):
    """Verifies that inbound telemetry with YouTube Shorts flips status to DISTRACTED."""
    mock_ws = AsyncMock()
    reg = ClientRegistration(
        client_id="LAB-PC-02",
        hostname="PC-02",
        ip_address="192.168.1.51",
    )
    await manager.register_workstation(reg, mock_ws)

    telemetry = TelemetryPayload(
        client_id="LAB-PC-02",
        cpu_percent=15.0,
        ram_percent=45.0,
        active_window_title="YouTube Shorts - Funny Moments",
        active_process_name="chrome.exe",
    )
    updated = await manager.record_telemetry(telemetry)
    assert updated.status == WorkstationStatus.DISTRACTED
    assert updated.violation_count == 1
    assert updated.distraction_report.is_distracted is True


@pytest.mark.asyncio
async def test_heartbeat_timeout_watchdog_tamper_alert(manager: LabConnectionManager):
    """Verifies that missing heartbeats exceeding timeout threshold generate tamper alerts."""
    mock_ws = AsyncMock()
    reg = ClientRegistration(
        client_id="LAB-PC-03",
        hostname="PC-03",
        ip_address="192.168.1.52",
    )
    await manager.register_workstation(reg, mock_ws)

    # Artificially age the heartbeat to 25 seconds ago
    state = manager.get_workstation("LAB-PC-03")
    assert state is not None
    state.last_heartbeat = datetime.now(timezone.utc) - timedelta(seconds=25)

    # Run watchdog with 15s threshold
    alerts = await manager.check_heartbeat_timeouts(timeout_seconds=15.0)
    assert len(alerts) == 1
    assert alerts[0].client_id == "LAB-PC-03"
    assert "HEARTBEAT_TIMEOUT_TAMPER" in alerts[0].alert_type
    assert state.status == WorkstationStatus.DISCONNECTED_TAMPERED

    # Acknowledge alert
    ack_res = manager.acknowledge_alert(alerts[0].alert_id)
    assert ack_res is True
    assert len(manager.get_active_alerts()) == 0


@pytest.mark.asyncio
async def test_command_dispatch_locks_state(manager: LabConnectionManager):
    """Verifies that LOCK command dispatches over WebSocket and updates workstation state."""
    mock_ws = AsyncMock()
    mock_ws.send_text = AsyncMock()

    reg = ClientRegistration(
        client_id="LAB-PC-04",
        hostname="PC-04",
        ip_address="192.168.1.53",
    )
    await manager.register_workstation(reg, mock_ws)

    cmd = AdminCommandPayload(command=CommandType.LOCK, message="Curfew screen lock")
    success = await manager.send_command_to_client("LAB-PC-04", cmd)

    assert success is True
    mock_ws.send_text.assert_called_once()
    state = manager.get_workstation("LAB-PC-04")
    assert state.curfew_locked is True
    assert state.status == WorkstationStatus.CURFEW_LOCKED
