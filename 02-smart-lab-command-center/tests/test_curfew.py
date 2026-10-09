"""Module: tests/test_curfew.py
Description: Unit and boundary verification tests for 21:00 Curfew Policy Engine.
Adheres to AGENTS.md: Boundary threshold testing, determinism via injected datetimes.
"""

from datetime import datetime
import pytest

from server.curfew import CurfewDecision, CurfewEngine, CurfewStage
from server.schemas import CommandType, CurfewConfig


@pytest.fixture
def curfew() -> CurfewEngine:
    return CurfewEngine()


def _make_dt(hour: int, minute: int, second: int = 0) -> datetime:
    """Helper creating a fixed datetime on an arbitrary day with given local time."""
    return datetime(2026, 10, 9, hour, minute, second)


def test_normal_operating_hours(curfew: CurfewEngine):
    """Asserts that regular afternoon and evening hours are marked NORMAL."""
    dt_afternoon = _make_dt(15, 30)
    decision = curfew.evaluate(dt_afternoon)
    assert decision.stage == CurfewStage.NORMAL
    assert decision.action_required is False
    assert decision.suggested_command is None


def test_curfew_10m_warning_boundary(curfew: CurfewEngine):
    """Asserts that 20:50 triggers the 10-minute preparatory warning."""
    dt_10m = _make_dt(20, 50, 0)
    decision = curfew.evaluate(dt_10m)
    assert decision.stage == CurfewStage.WARNING_10M
    assert decision.action_required is True
    assert decision.suggested_command == CommandType.BROADCAST_MESSAGE
    assert "10 minutes" in decision.broadcast_message


def test_curfew_2m_warning_boundary(curfew: CurfewEngine):
    """Asserts that 20:58 triggers the 2-minute urgent save warning."""
    dt_2m = _make_dt(20, 58, 0)
    decision = curfew.evaluate(dt_2m)
    assert decision.stage == CurfewStage.WARNING_2M
    assert decision.action_required is True
    assert decision.suggested_command == CommandType.BROADCAST_MESSAGE
    assert "2 minutes" in decision.broadcast_message


def test_curfew_lock_exact_boundary(curfew: CurfewEngine):
    """Asserts that exactly at 21:00 (and until 21:04:59) the screen lock command is issued."""
    dt_lock = _make_dt(21, 0, 0)
    decision = curfew.evaluate(dt_lock)
    assert decision.stage == CurfewStage.CURFEW_LOCKED
    assert decision.action_required is True
    assert decision.suggested_command == CommandType.LOCK

    dt_lock_late = _make_dt(21, 4, 59)
    decision_late = curfew.evaluate(dt_lock_late)
    assert decision_late.stage == CurfewStage.CURFEW_LOCKED
    assert decision_late.suggested_command == CommandType.LOCK


def test_curfew_auto_shutdown_trigger(curfew: CurfewEngine):
    """Asserts that at 21:05 graceful automated shutdown is initiated."""
    dt_shutdown = _make_dt(21, 5, 0)
    decision = curfew.evaluate(dt_shutdown)
    assert decision.stage == CurfewStage.AUTO_SHUTDOWN
    assert decision.action_required is True
    assert decision.suggested_command == CommandType.SHUTDOWN


def test_curfew_overnight_hours(curfew: CurfewEngine):
    """Asserts that late-night/overnight hours (e.g. 02:00 AM) remain in AUTO_SHUTDOWN."""
    dt_night = _make_dt(2, 30, 0)
    decision = curfew.evaluate(dt_night)
    assert decision.stage == CurfewStage.AUTO_SHUTDOWN
    assert decision.action_required is True
    assert decision.suggested_command == CommandType.SHUTDOWN


def test_instructor_curfew_override(curfew: CurfewEngine):
    """Asserts that an active instructor override suspends curfew actions even past 21:00."""
    curfew.set_override(active=True, reason="Extended Final Exam Session")
    dt_exam = _make_dt(21, 15, 0)

    decision = curfew.evaluate(dt_exam)
    assert decision.stage == CurfewStage.OVERRIDE
    assert decision.action_required is False
    assert decision.suggested_command is None
    assert "Extended Final Exam Session" in decision.reason


def test_curfew_morning_reopen_boundary(curfew: CurfewEngine):
    """Asserts that lab curfew ends and normal operations resume at 08:00 AM."""
    # 07:59:59 AM -> Still in overnight curfew shutdown
    dt_before_open = _make_dt(7, 59, 59)
    dec_before = curfew.evaluate(dt_before_open)
    assert dec_before.stage == CurfewStage.AUTO_SHUTDOWN
    assert dec_before.action_required is True

    # 08:00:00 AM -> Reopened, NORMAL operations
    dt_open = _make_dt(8, 0, 0)
    dec_open = curfew.evaluate(dt_open)
    assert dec_open.stage == CurfewStage.NORMAL
    assert dec_open.action_required is False
    assert dec_open.suggested_command is None

