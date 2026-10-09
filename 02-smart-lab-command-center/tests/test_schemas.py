"""Module: tests/test_schemas.py
Description: Unit and negative tests for server/schemas.py data contracts.
Adheres to AGENTS.md Section 5: Negative testing & edge cases, Pydantic runtime boundaries.
"""

from datetime import datetime, timezone
import pytest
from pydantic import ValidationError

from server.schemas import (
    AdminCommandPayload,
    ClientRegistration,
    CommandType,
    CurfewConfig,
    DistractionCategory,
    DistractionReport,
    TelemetryPayload,
    WorkstationState,
    WorkstationStatus,
)


def test_client_registration_valid():
    """Asserts valid client registration succeeds."""
    reg = ClientRegistration(
        client_id="LAB-PC-01",
        hostname="PC-AS-SUNNAH-01",
        ip_address="192.168.1.105",
        os_info="Windows 11 Education",
        student_name="Zubair Ahmed",
        agent_version="1.0.0",
    )
    assert reg.client_id == "LAB-PC-01"
    assert reg.ip_address == "192.168.1.105"


@pytest.mark.parametrize(
    "invalid_ip",
    [
        "999.999.999.999",
        "192.168.1",
        "not-an-ip",
        "192.168.1.256",
        "",
        "192.168.1.-1",
    ],
)
def test_client_registration_invalid_ipv4(invalid_ip: str):
    """Negative test: Asserts malformed IPv4 addresses fail schema validation."""
    with pytest.raises(ValidationError):
        ClientRegistration(
            client_id="PC-01",
            hostname="HOST-01",
            ip_address=invalid_ip,
        )


@pytest.mark.parametrize("empty_val", ["", "   ", "\t\n"])
def test_client_registration_empty_strings(empty_val: str):
    """Negative test: Asserts empty or whitespace-only client IDs and hostnames are rejected."""
    with pytest.raises(ValidationError):
        ClientRegistration(
            client_id=empty_val,
            hostname="Valid-Host",
            ip_address="192.168.1.1",
        )


def test_telemetry_payload_boundary_values():
    """Validates CPU/RAM boundary values (0.0 to 100.0)."""
    # Exact boundaries
    p_min = TelemetryPayload(client_id="PC-01", cpu_percent=0.0, ram_percent=0.0)
    assert p_min.cpu_percent == 0.0
    assert p_min.ram_percent == 0.0

    p_max = TelemetryPayload(client_id="PC-01", cpu_percent=100.0, ram_percent=100.0)
    assert p_max.cpu_percent == 100.0
    assert p_max.ram_percent == 100.0

    # Negative test: exceeding boundaries
    with pytest.raises(ValidationError):
        TelemetryPayload(client_id="PC-01", cpu_percent=-1.0, ram_percent=50.0)

    with pytest.raises(ValidationError):
        TelemetryPayload(client_id="PC-01", cpu_percent=50.0, ram_percent=100.1)


@pytest.mark.parametrize(
    "invalid_time",
    [
        "25:00",
        "21:60",
        "9:00",  # missing leading zero
        "21-00",
        "evening",
        "",
    ],
)
def test_curfew_config_invalid_time_format(invalid_time: str):
    """Negative test: Asserts invalid curfew timetable strings are rejected."""
    with pytest.raises(ValidationError):
        CurfewConfig(curfew_lock=invalid_time)


def test_admin_command_payload_defaults():
    """Asserts admin command defaults and timestamp generation."""
    cmd = AdminCommandPayload(command=CommandType.LOCK, message="Testing screen lock")
    assert cmd.command == CommandType.LOCK
    assert cmd.target_client_id is None  # Broadcast by default
    assert isinstance(cmd.issued_at, datetime)
