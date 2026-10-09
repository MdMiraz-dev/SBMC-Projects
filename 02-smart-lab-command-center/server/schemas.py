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
    CAPTURE_SCREEN = "CAPTURE_SCREEN"
    BROADCAST_FILE = "BROADCAST_FILE"
    COLLECT_ASSIGNMENTS = "COLLECT_ASSIGNMENTS"
    SET_USB_POLICY = "SET_USB_POLICY"
    SET_FOCUS_MODE = "SET_FOCUS_MODE"


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
    screen_thumbnail: Optional[str] = Field(default=None, description="Base64 encoded JPEG thumbnail data URI")
    usb_blocked: Optional[bool] = Field(default=False, description="Current USB mass storage block policy")
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
    screen_thumbnail: Optional[str] = None
    distraction_report: Optional[DistractionReport] = None
    violation_count: int = 0
    curfew_locked: bool = False
    productivity_score: int = 100
    usb_blocked: bool = False
    focus_mode_active: bool = False
    app_usage: Dict[str, "AppUsageRecord"] = Field(default_factory=dict)


class AppUsageRecord(BaseModel):
    """Time-tracking record for application usage per workstation."""
    client_id: str
    student_name: str
    process_name: str
    window_title: str
    category: DistractionCategory = DistractionCategory.ALLOWED
    total_seconds: int = Field(default=0, ge=0)
    first_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_distracted: bool = False


class AdminCommandPayload(BaseModel):
    """Typed administrative directive dispatched to one or all workstations."""
    command: CommandType
    target_client_id: Optional[str] = Field(default=None, description="None indicates broadcast to all active lab PCs")
    message: Optional[str] = Field(default=None, max_length=512, description="Pop-up message text for students")
    duration_seconds: Optional[int] = Field(default=None, ge=1, le=86400)
    target_process: Optional[str] = Field(default=None, max_length=128)
    extra_data: Optional[Dict[str, Any]] = Field(default=None, description="Optional extra data (file payload, usb settings)")
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
    morning_open: str = Field(default="08:00", description="HH:MM format for morning reopening")
    enabled: bool = True
    override_active: bool = False
    override_reason: Optional[str] = None

    @field_validator("warning_10m", "warning_2m", "curfew_lock", "auto_shutdown", "morning_open")
    @classmethod
    def validate_hh_mm(cls, v: str) -> str:
        if not re.match(r"^([01]\d|2[0-3]):([0-5]\d)$", v):
            raise ValueError(f"Invalid time format '{v}'. Expected 24-hour HH:MM format.")
        return v


# ==============================================================================
# Feature 1: Productivity & Daily Report Models
# ==============================================================================

class StudentProductivitySummary(BaseModel):
    """Productivity report card metrics for an individual student."""
    client_id: str
    student_name: str
    productivity_score: int = Field(..., ge=0, le=100)
    focused_seconds: int = 0
    distraction_seconds: int = 0
    violation_count: int = 0
    top_used_app: str = "System"
    status: WorkstationStatus = WorkstationStatus.ONLINE
    formatted_focused_time: str = "0s"
    formatted_distraction_time: str = "0s"


class DailyReport(BaseModel):
    """Consolidated institutional end-of-day productivity audit report."""
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    total_students: int = 0
    lab_average_score: int = 100
    total_focused_minutes: float = 0.0
    total_distraction_minutes: float = 0.0
    top_focused_students: List[StudentProductivitySummary] = Field(default_factory=list)
    top_distracted_students: List[StudentProductivitySummary] = Field(default_factory=list)
    category_breakdown: Dict[str, int] = Field(default_factory=dict)
    summary_text: str = ""


# ==============================================================================
# Feature 2: Focus Mode Request
# ==============================================================================

class FocusModeRequest(BaseModel):
    """Payload to toggle global distraction blocking focus mode."""
    active: bool
    reason: Optional[str] = "Instructor focused coding session"


# ==============================================================================
# Feature 3: Central File Broadcast & Assignment Collection Models
# ==============================================================================

class FileBroadcastPayload(BaseModel):
    """Payload for broadcasting lecture sheets or starter code to workstations."""
    filename: str = Field(..., min_length=1, max_length=256)
    file_content_base64: str = Field(..., min_length=1)
    target_folder: str = Field(default="lab_materials", max_length=128)
    sender: str = Field(default="Lab Instructor", max_length=64)
    file_size_bytes: int = 0
    description: Optional[str] = None


class AssignmentSubmissionPayload(BaseModel):
    """Workstation-to-server assignment file upload payload."""
    client_id: str
    student_name: str
    filename: str
    file_content_base64: str
    file_size_bytes: int = 0
    submitted_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CollectAssignmentsRequest(BaseModel):
    """Instructor directive to fetch student assignments from all PCs."""
    assignment_name: str = Field(default="submission.py", max_length=128)
    folder_path: str = Field(default="assignments", max_length=128)


# ==============================================================================
# Feature 4: USB Storage Policy Request
# ==============================================================================

class UsbPolicyRequest(BaseModel):
    """Policy request to block or allow USB mass storage."""
    blocked: bool
    target_client_id: Optional[str] = None
    reason: Optional[str] = "As-Sunnah Lab anti-malware and integrity policy"


# ==============================================================================
# Feature 5: Telegram Remote Control Simulator
# ==============================================================================

class TelegramSimulateRequest(BaseModel):
    """Simulates a Telegram bot slash command via HTTP for testing and dashboard control."""
    command: str = Field(..., description="e.g. /status, /lockall, /unlockall, /curfew, /report, /focus on")
    chat_id: Optional[str] = "admin_chat"
    user_name: Optional[str] = "LabInstructor"

