"""Module: server/telegram_bot.py
Description: Telegram Remote Control Command Router for Smart Lab Command Center.
Allows remote monitoring and instant admin control via Telegram Bot slash commands.
Adheres to AGENTS.md: Environment secrets isolation, safe execution, mockable testability.
"""

from datetime import datetime, timezone
import logging
import os
from typing import Any, Dict, Optional, Tuple

from .curfew import CurfewEngine
from .manager import LabConnectionManager
from .schemas import CommandType, AdminCommandPayload

logger = logging.getLogger("smart_lab.telegram")


class TelegramCommandRouter:
    """Processes incoming Telegram commands and interacts with central manager."""

    def __init__(self, manager: LabConnectionManager, curfew_engine: CurfewEngine):
        self.manager = manager
        self.curfew_engine = curfew_engine
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self.admin_chat_id = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").strip()

    @property
    def is_configured(self) -> bool:
        """Returns True if a real Telegram Bot token has been provided."""
        return bool(self.bot_token and len(self.bot_token) > 10)

    async def execute_command(self, raw_text: str, sender: str = "Telegram Admin") -> str:
        """
        Executes a Telegram command string (e.g. /status, /lockall, /curfew)
        and returns a markdown-formatted response message.
        """
        text = raw_text.strip()
        parts = text.split()
        if not parts:
            return "⚠️ Empty command received."

        cmd = parts[0].lower()
        arg = parts[1].lower() if len(parts) > 1 else None

        if cmd in ("/start", "/help"):
            return (
                "🖥️ *As-Sunnah Smart Lab Command Center — Telegram Bot*\n\n"
                "Available Remote Commands:\n"
                "• `/status` — Real-time lab overview, metrics & curfew state\n"
                "• `/lockall` — Instantly lock all student computer displays\n"
                "• `/unlockall` — Unlock all computer displays\n"
                "• `/shutdownall` — Broadcast graceful power off to lab\n"
                "• `/focus [on|off]` — One-click distraction blocking mode\n"
                "• `/usb [lock|unlock]` — USB storage restriction policy\n"
                "• `/curfew` — Check or toggle 21:00 curfew override\n"
                "• `/report` — Generate End-of-Day AI Productivity Card"
            )

        elif cmd == "/status":
            workstations = self.manager.get_all_workstations()
            total = len(workstations)
            online = sum(1 for w in workstations if w.status.value == "ONLINE")
            distracted = sum(1 for w in workstations if w.status.value == "DISTRACTED")
            tampered = sum(1 for w in workstations if w.status.value == "DISCONNECTED_TAMPERED")
            avg_score = round(sum(w.productivity_score for w in workstations) / total) if total > 0 else 100

            curfew_dec = self.curfew_engine.evaluate()

            return (
                "📊 *As-Sunnah Lab Status Report*\n"
                f"• *Registered PCs*: {total}\n"
                f"• *Online Active*: {online}\n"
                f"• *Distracted (Reels/Games)*: {distracted}\n"
                f"• *Tampered / Silent*: {tampered}\n"
                f"• *Avg Productivity Score*: {avg_score}/100\n"
                f"• *Focus Mode*: {'ENABLED 🎯' if self.manager.focus_mode_active else 'OFF'}\n"
                f"• *USB Policy*: {'BLOCKED 🔒' if self.manager.usb_storage_blocked else 'ALLOWED 💾'}\n"
                f"• *Curfew Stage*: `{curfew_dec.stage.value}` (Override: {self.curfew_engine.config.override_active})"
            )

        elif cmd == "/lockall":
            dispatched = await self.manager.broadcast_command(AdminCommandPayload(
                command=CommandType.LOCK,
                issued_by=f"Telegram ({sender})",
                message="All workstations locked via remote administrative directive.",
            ))
            return f"🔒 *Lock Dispatched*: Successfully locked screens on {dispatched} workstation(s)."

        elif cmd == "/unlockall":
            dispatched = await self.manager.broadcast_command(AdminCommandPayload(
                command=CommandType.UNLOCK,
                issued_by=f"Telegram ({sender})",
                message="Workstation unlocked by instructor.",
            ))
            return f"🔓 *Unlock Dispatched*: Successfully unlocked {dispatched} workstation(s)."

        elif cmd == "/shutdownall":
            dispatched = await self.manager.broadcast_command(AdminCommandPayload(
                command=CommandType.SHUTDOWN,
                issued_by=f"Telegram ({sender})",
                message="Lab closing. Workstations powering off.",
            ))
            return f"⚡ *Shutdown Dispatched*: Graceful power off command sent to {dispatched} workstation(s)."

        elif cmd == "/focus":
            target_state = True if arg == "on" else (False if arg == "off" else not self.manager.focus_mode_active)
            delivered = await self.manager.set_focus_mode(target_state, reason=f"Telegram toggle by {sender}")
            state_str = "ENABLED (Distractions Blocked) 🎯" if target_state else "DISABLED 🔓"
            return f"🎯 *Focus Mode*: {state_str} across {delivered} workstation(s)."

        elif cmd == "/usb":
            target_blocked = True if arg in ("lock", "block", "on") else (False if arg in ("unlock", "allow", "off") else not self.manager.usb_storage_blocked)
            delivered = await self.manager.set_usb_policy(target_blocked)
            state_str = "BLOCKED 🔒" if target_blocked else "ALLOWED 💾"
            return f"💾 *USB Storage Policy*: {state_str} across {delivered} workstation(s)."

        elif cmd == "/curfew":
            if arg in ("override", "toggle"):
                new_state = not self.curfew_engine.config.override_active
                self.curfew_engine.set_override(new_state, reason=f"Telegram toggle by {sender}")
                await self.manager.broadcast_admin_update()
                return f"⚙️ *Curfew Override*: {'ACTIVATED (Lab Open Past 21:00)' if new_state else 'DEACTIVATED (Enforcing 21:00 Curfew)'}"
            else:
                decision = self.curfew_engine.evaluate()
                return (
                    f"⏰ *Curfew Timetable Status*:\n"
                    f"• Schedule: 21:00 Lock/Shutdown → 08:00 AM Open\n"
                    f"• Current Stage: `{decision.stage.value}`\n"
                    f"• Override Active: `{self.curfew_engine.config.override_active}`\n"
                    f"• Details: {decision.reason}\n\n"
                    f"_Tip: Use `/curfew toggle` to extend or resume curfew._"
                )

        elif cmd == "/report":
            report = self.manager.generate_daily_report()
            top_focus_str = "\n".join(
                f"  • {s.student_name} ({s.client_id}): {s.productivity_score}% (Focused: {s.formatted_focused_time})"
                for s in report.top_focused_students[:3]
            ) or "  • No active students recorded yet."

            top_distract_str = "\n".join(
                f"  • {s.student_name} ({s.client_id}): {s.distraction_seconds}s distraction ({s.violation_count} alert(s))"
                for s in report.top_distracted_students[:3]
            ) or "  • None! All students remained focused."

            return (
                "📋 *Daily AI Productivity Report Card*\n\n"
                f"• *Lab Average Productivity*: {report.lab_average_score}/100\n"
                f"• *Active Workstations*: {report.total_students}\n"
                f"• *Total Focused Time*: {report.total_focused_minutes} min\n"
                f"• *Total Distraction Time*: {report.total_distraction_minutes} min\n\n"
                f"🏆 *Top Focused Students*:\n{top_focus_str}\n\n"
                f"⚠️ *Distraction Flagged*:\n{top_distract_str}"
            )

        return f"❓ Unknown command: `{cmd}`. Type `/help` for list of supported commands."
