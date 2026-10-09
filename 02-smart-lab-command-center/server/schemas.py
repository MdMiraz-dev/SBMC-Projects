"""Module: server/schemas.py
Description: Pydantic schemas and typed data contracts for Smart Lab Command Center.
Adheres to SBMC AGENTS.md: Strict typing, runtime boundary validation, zero untyped data.
"""

from datetime import datetime, timezone
from enum import Enum
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class WorkstationStatus(str, Enum):
    """Lifecycle and operational status of a lab computer."""
    ONLINE = "ONLINE"
    IDLE = "IDLE"
    DISTRACTED = "DISTRACTED"
    DISCONNECTED_TAMPERED = "DISCONNECTED_TAMPERED"
    CURFEW_LOCKED = "CURFEW_LOCKED"
    SHUTTING_DOWN = "SHUTTING_DOWN"


class CommandType(str, Enum):
    """Strictly enumerated remote administrative commands (no arbitrary execution)."""
    LOCK = "LOCK"
    UNLOCK = "UNLOCK"
    SHUTDOWN = "SHUTDOWN"
    REBOOT = "REBOOT"
    BROADCAST_MESSAGE = "BROADCAST_MESSAGE"
    KILL_PROCESS = "KILL_PROCESS"


class DistractionCategory(str, Enum):
    """Categorization for detected student activities."""
    ALLOWED = "ALLOWED"
    REELS_SHORTS = "REELS_SHORTS"
    SOCIAL_MEDIA = "SOCIAL_MEDIA"
    GAMING = "GAMING"
    STREAMING = "STREAMING"


class ClientRegistration(BaseModel):
    """Initial handshake registration sent by workstation agent upon connecting."""
    client_id: str = Field(..., min_length=2, max_length=64, description="Unique workstation identifier, e.g. LAB-PC-01")
    hostname: str = Field(..., min_length=1, max_length=128)
    ip_address: str = Field(..., description="Local IPv4 network address")
    os_info: str = Field(default="Windows 11 Pro", max_length=128)
    student_name: str = Field(default="Student Workstation", max_length=64)
    agent_version: str = Field(default="1.0.0", max_length=16)

    @field_validator("client_id", "hostname", "student_name")
    @classmethod
    def validate_non_empty(cls, v: str) -> str:
        stripped = v.strip()
        if not stripped:
            raise ValueError("Field cannot be empty or pure whitespace.")
        return stripped

    @field_validator("ip_address")
    @classmethod
    def validate_ipv4(cls, v: str) -> str:
        stripped = v.strip()
        # Basic IPv4 format validation
        parts = stripped.split(".")
        if len(parts) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
            raise ValueError(f"Invalid IPv4 address format: {v}")
        return stripped


class TelemetryPayload(BaseModel):
    """Periodic telemetry report emitted every heartbeat interval."""
    client_id: str = Field(..., min_length=2, max_length=64)
    cpu_percent: float = Field(..., ge=0.0, le=100.0, description="CPU usage percentage")
    ram_percent: float = Field(..., ge=0.0, le=100.0, description="RAM usage percentage")
    active_window_title: str = Field(default="", max_length=512)
    active_process_name: str = Field(default="", max_length=128)
    is_idle: bool = Field(default=False)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("active_window_title", "active_process_name")
    @classmethod
    def sanitize_strings(cls, v: str) -> str:
        return v.strip()


class DistractionReport(BaseModel):
    """Evaluation result from Distraction Heuristics Engine."""
    is_distracted: bool = False
    category: DistractionCategory = DistractionCategory.ALLOWED
    flagged_title: str = ""
    matched_keyword: Optional[str] = None
    severity: str = "INFO"  # INFO, WARNING, CRITICAL
    message: str = "Active window compliant with educational policy."


class WorkstationState(BaseModel):
    """Full server-side in-memory snapshot of a workstation."""
    client_id: str
    hostname: str
    ip_address: str
    student_name: str
    os_info: str = "Windows 11"
    status: WorkstationStatus = WorkstationStatus.ONLINE
    last_heartbeat: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    latest_telemetry: Optional[TelemetryPayload] = None
    distraction_report: Optional[DistractionReport] = None
    violation_count: int = 0
    curfew_locked: bool = False


class AdminCommandPayload(BaseModel):
    """Typed administrative directive dispatched to one or all workstations."""
    command: CommandType
    target_client_id: Optional[str] = Field(default=None, description="None indicates broadcast to all active lab PCs")
    message: Optional[str] = Field(default=None, max_length=512, description="Pop-up message text for students")
    duration_seconds: Optional[int] = Field(default=None, ge=1, le=86400)
    target_process: Optional[str] = Field(default=None, max_length=128)
    issued_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    issued_by: str = Field(default="Lab Admin", max_length=64)


class TamperAlertEvent(BaseModel):
    """Tamper or disconnection alert record logged by watchdog."""
    alert_id: str
    client_id: str
    hostname: str
    ip_address: str
    alert_type: str = "HEARTBEAT_DISCONNECT_TAMPER"
    last_seen: datetime
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    message: str
    acknowledged: bool = False


class CurfewConfig(BaseModel):
    """Curfew schedule and policy configuration."""
    warning_10m: str = Field(default="20:50", description="HH:MM format for 10-minute warning")
    warning_2m: str = Field(default="20:58", description="HH:MM format for 2-minute warning")
    curfew_lock: str = Field(default="21:00", description="HH:MM format for screen lock")
    auto_shutdown: str = Field(default="21:05", description="HH:MM format for lab shutdown")
    enabled: bool = True
    override_active: bool = False
    override_reason: Optional[str] = None

    @field_validator("warning_10m", "warning_2m", "curfew_lock", "auto_shutdown")
    @classmethod
    def validate_hh_mm(cls, v: str) -> str:
        if not re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", v):
            raise ValueError(f"Invalid time format '{v}'. Expected 24-hour HH:MM format.")
        return v
