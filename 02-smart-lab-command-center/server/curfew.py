"""Module: server/curfew.py
Description: Automated Curfew and Lab Shutdown Policy Engine.
Enforces 20:50 warning, 20:58 final warning, 21:00 curfew lock, and 21:05 auto-shutdown.
Adheres to AGENTS.md: Pure functions, testable time injection, clean state transitions.
"""

from datetime import datetime, time, timezone
from enum import Enum
from typing import Optional, Tuple
from .schemas import CommandType, CurfewConfig


class CurfewStage(str, Enum):
    """Stages of the lab daily curfew workflow."""
    NORMAL = "NORMAL"
    WARNING_10M = "WARNING_10M"
    WARNING_2M = "WARNING_2M"
    CURFEW_LOCKED = "CURFEW_LOCKED"
    AUTO_SHUTDOWN = "AUTO_SHUTDOWN"
    OVERRIDE = "OVERRIDE"


class CurfewDecision:
    """Result of curfew evaluation for the current moment."""

    def __init__(
        self,
        stage: CurfewStage,
        action_required: bool = False,
        suggested_command: Optional[CommandType] = None,
        broadcast_message: Optional[str] = None,
        reason: str = "",
    ):
        self.stage = stage
        self.action_required = action_required
        self.suggested_command = suggested_command
        self.broadcast_message = broadcast_message
        self.reason = reason

    def __repr__(self) -> str:
        return f"<CurfewDecision stage={self.stage.value} action={self.action_required} cmd={self.suggested_command}>"


class CurfewEngine:
    """Evaluates and manages the 21:00 (9:00 PM) As-Sunnah Computer Lab Curfew."""

    def __init__(self, config: Optional[CurfewConfig] = None):
        self.config: CurfewConfig = config or CurfewConfig()

    def set_override(self, active: bool, reason: str = "Instructor extended session") -> None:
        """Sets or clears administrative curfew override."""
        self.config.override_active = active
        self.config.override_reason = reason if active else None

    def update_config(self, new_config: CurfewConfig) -> None:
        """Updates curfew timetable and parameters."""
        self.config = new_config

    @staticmethod
    def _parse_time(hh_mm: str) -> time:
        parts = hh_mm.split(":")
        return time(hour=int(parts[0]), minute=int(parts[1]))

    def evaluate(self, current_dt: Optional[datetime] = None) -> CurfewDecision:
        """
        Evaluates current time against configured curfew schedule.
        Accepts injected datetime for deterministic unit and negative testing.
        """
        if not self.config.enabled:
            return CurfewDecision(
                stage=CurfewStage.NORMAL,
                reason="Curfew policy disabled by lab configuration.",
            )

        if self.config.override_active:
            return CurfewDecision(
                stage=CurfewStage.OVERRIDE,
                reason=f"Curfew overridden by instructor: {self.config.override_reason or 'Authorized'}",
            )

        now = current_dt.time() if current_dt else datetime.now().time()

        t_10m = self._parse_time(self.config.warning_10m)
        t_2m = self._parse_time(self.config.warning_2m)
        t_lock = self._parse_time(self.config.curfew_lock)
        t_shutdown = self._parse_time(self.config.auto_shutdown)
        t_morning_open = time(6, 0)  # Lab opens at 06:00 AM

        # Case 1: Post 21:05 (Shutdown trigger until morning 06:00)
        if (now >= t_shutdown) or (now < t_morning_open):
            return CurfewDecision(
                stage=CurfewStage.AUTO_SHUTDOWN,
                action_required=True,
                suggested_command=CommandType.SHUTDOWN,
                broadcast_message="Curfew 21:05 reached. As-Sunnah Smart Lab automated graceful shutdown initiated.",
                reason="Curfew auto-shutdown hour reached. Workstations powering down.",
            )

        # Case 2: 21:00 to 21:04:59 (Curfew Screen Lock)
        if t_lock <= now < t_shutdown:
            return CurfewDecision(
                stage=CurfewStage.CURFEW_LOCKED,
                action_required=True,
                suggested_command=CommandType.LOCK,
                broadcast_message="9:00 PM Curfew in effect. Lab screens locked for maintenance and security.",
                reason="21:00 Curfew lock active.",
            )

        # Case 3: 20:58 to 20:59:59 (2-Minute Warning)
        if t_2m <= now < t_lock:
            return CurfewDecision(
                stage=CurfewStage.WARNING_2M,
                action_required=True,
                suggested_command=CommandType.BROADCAST_MESSAGE,
                broadcast_message="⚠️ Attention Students: Lab closing in 2 minutes! Save all documents immediately.",
                reason="20:58 2-minute urgent curfew warning.",
            )

        # Case 4: 20:50 to 20:57:59 (10-Minute Warning)
        if t_10m <= now < t_2m:
            return CurfewDecision(
                stage=CurfewStage.WARNING_10M,
                action_required=True,
                suggested_command=CommandType.BROADCAST_MESSAGE,
                broadcast_message="📢 Notice: Lab curfew begins at 21:00 (10 minutes remaining). Please begin saving your work.",
                reason="20:50 10-minute preparatory curfew warning.",
            )

        # Case 5: Normal Operational Hours (06:00 to 20:49:59)
        return CurfewDecision(
            stage=CurfewStage.NORMAL,
            reason="Within standard lab operating hours.",
        )
