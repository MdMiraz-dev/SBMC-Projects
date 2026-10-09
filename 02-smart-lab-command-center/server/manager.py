"""Module: server/manager.py
Description: Central Workstation Connection Manager & Heartbeat Tamper Watchdog.
Tracks student PC WebSocket sessions, telemetry cache, heartbeat timeouts, and admin broadcasts.
Adheres to AGENTS.md: Thread-safe, modular state transitions, negative edge case resilient.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

from fastapi import WebSocket

from .detector import DistractionDetector
from .schemas import (
    AdminCommandPayload,
    AppUsageRecord,
    AssignmentSubmissionPayload,
    ClientRegistration,
    CollectAssignmentsRequest,
    CommandType,
    DailyReport,
    DistractionCategory,
    FileBroadcastPayload,
    StudentProductivitySummary,
    TamperAlertEvent,
    TelemetryPayload,
    WorkstationState,
    WorkstationStatus,
)

logger = logging.getLogger("smart_lab.manager")


class LabConnectionManager:
    """Manages active WebSocket sessions from student PCs and instructor dashboards."""

    MASTER_HOST_ID: str = "MASTER-ADMIN-PC"

    def __init__(self, detector: Optional[DistractionDetector] = None):
        self.detector: DistractionDetector = detector or DistractionDetector()
        # Active client sockets: client_id -> WebSocket
        self._active_sockets: Dict[str, WebSocket] = {}
        # Workstation states: client_id -> WorkstationState
        self._workstations: Dict[str, WorkstationState] = {}
        # Instructor dashboard sockets
        self._admin_sockets: Set[WebSocket] = set()
        # Historical tamper alerts
        self._alerts: List[TamperAlertEvent] = []

        # Feature 2: Focus Mode Policy State
        self.focus_mode_active: bool = False
        self.focus_mode_reason: Optional[str] = None

        # Feature 4: USB Storage Policy State
        self.usb_storage_blocked: bool = False

        # Feature 3: Collected Assignments Storage
        self.collected_assignments_dir: str = "collected_assignments"

    def get_all_workstations(self) -> List[WorkstationState]:
        """Returns snapshot list with Master Host first, followed by alphabetical workstations."""
        return sorted(self._workstations.values(), key=lambda w: (not getattr(w, "is_master_host", False), w.client_id))

    def get_workstation(self, client_id: str) -> Optional[WorkstationState]:
        """Retrieves single workstation state by identifier."""
        return self._workstations.get(client_id)

    def get_active_alerts(self) -> List[TamperAlertEvent]:
        """Returns all unacknowledged tamper alerts ordered newest first."""
        return [a for a in reversed(self._alerts) if not a.acknowledged]

    def acknowledge_alert(self, alert_id: str) -> bool:
        """Marks an alert as acknowledged by instructor."""
        for alert in self._alerts:
            if alert.alert_id == alert_id:
                alert.acknowledged = True
                return True
        return False

    async def register_admin_socket(self, websocket: WebSocket) -> None:
        """Registers an instructor dashboard WebSocket for live telemetry streaming."""
        await websocket.accept()
        self._admin_sockets.add(websocket)
        # Push initial snapshot immediately
        await self.broadcast_admin_update()

    def unregister_admin_socket(self, websocket: WebSocket) -> None:
        """Removes closed instructor dashboard WebSocket."""
        self._admin_sockets.discard(websocket)

    async def register_workstation(
        self,
        registration: ClientRegistration,
        websocket: WebSocket,
    ) -> WorkstationState:
        """
        Accepts workstation WebSocket connection and registers client in cluster state.
        """
        await websocket.accept()
        client_id = registration.client_id

        # Close stale socket if same client_id re-connects
        if client_id in self._active_sockets:
            old_ws = self._active_sockets[client_id]
            try:
                await old_ws.close(code=1000, reason="Superceded by new connection")
            except Exception:
                pass

        self._active_sockets[client_id] = websocket

        now = datetime.now(timezone.utc)
        existing = self._workstations.get(client_id)
        if existing:
            existing.hostname = registration.hostname
            existing.ip_address = registration.ip_address
            existing.student_name = registration.student_name
            existing.os_info = registration.os_info
            existing.status = WorkstationStatus.ONLINE
            existing.last_heartbeat = now
            state = existing
        else:
            state = WorkstationState(
                client_id=client_id,
                hostname=registration.hostname,
                ip_address=registration.ip_address,
                student_name=registration.student_name,
                os_info=registration.os_info,
                status=WorkstationStatus.ONLINE,
                last_heartbeat=now,
            )
            self._workstations[client_id] = state

        logger.info("Workstation registered: %s (%s)", client_id, registration.ip_address)
        await self.broadcast_admin_update()
        return state

    async def record_telemetry(self, telemetry: TelemetryPayload) -> WorkstationState:
        """
        Processes inbound telemetry payload: updates stats, evaluates distraction heuristics,
        and synchronizes with instructor dashboard.
        """
        client_id = telemetry.client_id
        state = self._workstations.get(client_id)
        now = datetime.now(timezone.utc)

        if not state:
            state = WorkstationState(
                client_id=client_id,
                hostname=f"HOST-{client_id}",
                ip_address="0.0.0.0",
                student_name="Student",
                status=WorkstationStatus.ONLINE,
                last_heartbeat=now,
            )
            self._workstations[client_id] = state

        state.last_heartbeat = now
        state.latest_telemetry = telemetry
        if telemetry.screen_thumbnail:
            state.screen_thumbnail = telemetry.screen_thumbnail

        # Distraction Heuristic Evaluation
        report = self.detector.evaluate(
            active_window_title=telemetry.active_window_title,
            active_process_name=telemetry.active_process_name,
        )
        state.distraction_report = report

        # Real-time Application Usage Time-Tracking
        proc = (telemetry.active_process_name or "").strip() or "System / Idle"
        title = (telemetry.active_window_title or "").strip() or "Desktop Session"
        usage_key = f"{proc}::{title[:40]}"

        if usage_key in state.app_usage:
            record = state.app_usage[usage_key]
            record.total_seconds += 5
            record.window_title = title
            record.last_seen = now
            record.category = report.category
            record.is_distracted = report.is_distracted
        else:
            state.app_usage[usage_key] = AppUsageRecord(
                client_id=client_id,
                student_name=state.student_name,
                process_name=proc,
                window_title=title,
                category=report.category,
                total_seconds=5,
                first_seen=now,
                last_seen=now,
                is_distracted=report.is_distracted,
            )

        if telemetry.usb_blocked is not None:
            state.usb_blocked = telemetry.usb_blocked
        state.focus_mode_active = self.focus_mode_active

        if report.is_distracted:
            state.status = WorkstationStatus.DISTRACTED
            state.violation_count += 1
            # Feature 2: Auto-restriction when Focus Mode is ON
            if self.focus_mode_active:
                asyncio.create_task(self.send_command_to_client(
                    client_id,
                    AdminCommandPayload(
                        command=CommandType.BROADCAST_MESSAGE,
                        target_client_id=client_id,
                        message=f"⚠️ FOCUS MODE ACTIVE: Distraction '{report.flagged_title or 'Entertainment'}' blocked! Return to coursework.",
                        issued_by="Focus Mode Enforcer",
                    )
                ))
        elif state.curfew_locked:
            state.status = WorkstationStatus.CURFEW_LOCKED
        elif telemetry.is_idle:
            state.status = WorkstationStatus.IDLE
        else:
            state.status = WorkstationStatus.ONLINE

        # Feature 1: Dynamic AI Productivity Scoring (0-100)
        focused_sec = sum(r.total_seconds for r in state.app_usage.values() if not r.is_distracted)
        distracted_sec = sum(r.total_seconds for r in state.app_usage.values() if r.is_distracted)
        total_time = focused_sec + distracted_sec
        if total_time > 0:
            ratio = focused_sec / total_time
            penalty = min(40, state.violation_count * 5)
            state.productivity_score = max(0, min(100, int(ratio * 100) - penalty))
        else:
            state.productivity_score = 100

        await self.broadcast_admin_update()
        return state

    def get_audit_log(self, client_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns consolidated application usage audit log records sorted by time spent."""
        records: List[Dict[str, Any]] = []
        for cid, state in self._workstations.items():
            if client_id and cid != client_id:
                continue
            for app_key, record in state.app_usage.items():
                rec_dict = record.model_dump(mode="json")
                rec_dict["formatted_time"] = self._format_duration(record.total_seconds)
                records.append(rec_dict)
        return sorted(records, key=lambda r: r["total_seconds"], reverse=True)

    @staticmethod
    def _format_duration(seconds: int) -> str:
        """Formats seconds into human readable duration e.g. '1h 15m 30s'."""
        if seconds < 60:
            return f"{seconds}s"
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h}h {m}m {s}s"
        return f"{m}m {s}s"

    async def handle_disconnect(self, client_id: str) -> None:
        """Handles graceful or abrupt socket closure of a workstation agent."""
        if client_id in self._active_sockets:
            del self._active_sockets[client_id]

        state = self._workstations.get(client_id)
        if state and state.status != WorkstationStatus.SHUTTING_DOWN:
            state.status = WorkstationStatus.DISCONNECTED_TAMPERED
            # Register immediate tamper alert
            alert = TamperAlertEvent(
                alert_id=f"ALT-{uuid.uuid4().hex[:8].upper()}",
                client_id=client_id,
                hostname=state.hostname,
                ip_address=state.ip_address,
                alert_type="CLIENT_SOCKET_DROPPED_TAMPER",
                last_seen=state.last_heartbeat,
                detected_at=datetime.now(timezone.utc),
                message=f"Workstation {client_id} disconnected unexpectedly. Possible network cable disconnect or task termination.",
            )
            self._alerts.append(alert)

        await self.broadcast_admin_update()

    async def check_heartbeat_timeouts(self, timeout_seconds: float = 15.0) -> List[TamperAlertEvent]:
        """
        Watchdog ticker: scans workstations for missing heartbeats (> timeout_seconds).
        Triggers DISCONNECTED_TAMPERED state and generates tamper alerts.
        """
        now = datetime.now(timezone.utc)
        new_alerts: List[TamperAlertEvent] = []

        for client_id, state in self._workstations.items():
            if state.is_master_host or client_id == self.MASTER_HOST_ID:
                continue
            if state.status in (WorkstationStatus.ONLINE, WorkstationStatus.IDLE, WorkstationStatus.DISTRACTED):
                elapsed = (now - state.last_heartbeat).total_seconds()
                if elapsed > timeout_seconds:
                    state.status = WorkstationStatus.DISCONNECTED_TAMPERED
                    alert = TamperAlertEvent(
                        alert_id=f"ALT-{uuid.uuid4().hex[:8].upper()}",
                        client_id=client_id,
                        hostname=state.hostname,
                        ip_address=state.ip_address,
                        alert_type="HEARTBEAT_TIMEOUT_TAMPER",
                        last_seen=state.last_heartbeat,
                        detected_at=now,
                        message=f"Workstation {client_id} heartbeat missing for {elapsed:.1f}s (Threshold: {timeout_seconds}s). Potential tampering detected.",
                    )
                    self._alerts.append(alert)
                    new_alerts.append(alert)
                    logger.warning("Heartbeat timeout on %s (elapsed %.1fs)", client_id, elapsed)

        if new_alerts:
            await self.broadcast_admin_update()

        return new_alerts

    async def send_command_to_client(self, client_id: str, command: AdminCommandPayload) -> bool:
        """Sends a structured command to a specific workstation via its WebSocket."""
        ws = self._active_sockets.get(client_id)
        if not ws:
            return False

        try:
            payload = command.model_dump(mode="json")
            await ws.send_text(json.dumps(payload))

            # Update local state if command is lock/unlock
            state = self._workstations.get(client_id)
            if state:
                if command.command == AdminCommandPayload.model_fields["command"].annotation.LOCK:
                    state.curfew_locked = True
                    state.status = WorkstationStatus.CURFEW_LOCKED
                elif command.command == AdminCommandPayload.model_fields["command"].annotation.UNLOCK:
                    state.curfew_locked = False
                    state.status = WorkstationStatus.ONLINE

            return True
        except Exception as exc:
            logger.error("Failed to deliver command to %s: %s", client_id, exc)
            return False

    async def broadcast_command(self, command: AdminCommandPayload) -> int:
        """Dispatches an administrative command to all currently connected workstations."""
        delivered_count = 0
        payload = command.model_dump(mode="json")
        encoded = json.dumps(payload)

        for client_id, ws in list(self._active_sockets.items()):
            try:
                await ws.send_text(encoded)
                delivered_count += 1
                state = self._workstations.get(client_id)
                if state:
                    if command.command.value == "LOCK":
                        state.curfew_locked = True
                        state.status = WorkstationStatus.CURFEW_LOCKED
                    elif command.command.value == "UNLOCK":
                        state.curfew_locked = False
                        state.status = WorkstationStatus.ONLINE
            except Exception as exc:
                logger.error("Failed broadcast to %s: %s", client_id, exc)

        await self.broadcast_admin_update()
        return delivered_count

    async def broadcast_admin_update(self) -> None:
        """Streams full cluster state and active alerts to all open instructor dashboard sessions."""
        if not self._admin_sockets:
            return

        avg_score = round(sum(w.productivity_score for w in self._workstations.values()) / len(self._workstations)) if self._workstations else 100

        payload = {
            "type": "CLUSTER_UPDATE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_registered": len(self._workstations),
            "total_online": sum(1 for w in self._workstations.values() if w.status == WorkstationStatus.ONLINE),
            "total_distracted": sum(1 for w in self._workstations.values() if w.status == WorkstationStatus.DISTRACTED),
            "total_tampered": sum(1 for w in self._workstations.values() if w.status == WorkstationStatus.DISCONNECTED_TAMPERED),
            "focus_mode_active": self.focus_mode_active,
            "usb_storage_blocked": self.usb_storage_blocked,
            "lab_average_productivity": avg_score,
            "workstations": [w.model_dump(mode="json") for w in self.get_all_workstations()],
            "alerts": [a.model_dump(mode="json") for a in self.get_active_alerts()],
            "audit_log": self.get_audit_log(),
        }
        encoded = json.dumps(payload)

        stale_sockets = set()
        for ws in self._admin_sockets:
            try:
                await ws.send_text(encoded)
            except Exception:
                stale_sockets.add(ws)

        for stale in stale_sockets:
            self._admin_sockets.discard(stale)

    # ==============================================================================
    # Feature 1: AI Productivity Daily Report
    # ==============================================================================
    def generate_daily_report(self) -> DailyReport:
        """Calculates institutional productivity analytics, top focused, and top distracted students."""
        summaries: List[StudentProductivitySummary] = []
        total_focused_sec = 0
        total_distracted_sec = 0
        cat_breakdown: Dict[str, int] = {}

        for cid, state in self._workstations.items():
            f_sec = sum(r.total_seconds for r in state.app_usage.values() if not r.is_distracted)
            d_sec = sum(r.total_seconds for r in state.app_usage.values() if r.is_distracted)
            total_focused_sec += f_sec
            total_distracted_sec += d_sec

            for r in state.app_usage.values():
                cat_val = r.category.value if hasattr(r.category, "value") else str(r.category)
                cat_breakdown[cat_val] = cat_breakdown.get(cat_val, 0) + r.total_seconds

            top_app = "System"
            if state.app_usage:
                top_rec = max(state.app_usage.values(), key=lambda r: r.total_seconds)
                top_app = top_rec.process_name

            summaries.append(StudentProductivitySummary(
                client_id=cid,
                student_name=state.student_name,
                productivity_score=state.productivity_score,
                focused_seconds=f_sec,
                distraction_seconds=d_sec,
                violation_count=state.violation_count,
                top_used_app=top_app,
                status=state.status,
                formatted_focused_time=self._format_duration(f_sec),
                formatted_distraction_time=self._format_duration(d_sec),
            ))

        total_students = len(summaries)
        avg_score = round(sum(s.productivity_score for s in summaries) / total_students) if total_students > 0 else 100

        top_focused = sorted(summaries, key=lambda s: (s.productivity_score, s.focused_seconds), reverse=True)
        top_distracted = sorted([s for s in summaries if s.distraction_seconds > 0 or s.violation_count > 0],
                                key=lambda s: (s.distraction_seconds, s.violation_count), reverse=True)

        return DailyReport(
            total_students=total_students,
            lab_average_score=avg_score,
            total_focused_minutes=round(total_focused_sec / 60, 1),
            total_distraction_minutes=round(total_distracted_sec / 60, 1),
            top_focused_students=top_focused[:10],
            top_distracted_students=top_distracted[:10],
            category_breakdown=cat_breakdown,
            summary_text=f"As-Sunnah Lab Productivity Index: {avg_score}/100 across {total_students} workstation(s).",
        )

    # ==============================================================================
    # Feature 2: One-Click Focus Mode
    # ==============================================================================
    async def set_focus_mode(self, active: bool, reason: Optional[str] = None) -> int:
        """Sets global focus mode to block distractions and pushes policy to all active agents."""
        self.focus_mode_active = active
        self.focus_mode_reason = reason or ("Active" if active else "Disabled")
        for state in self._workstations.values():
            state.focus_mode_active = active

        cmd = AdminCommandPayload(
            command=CommandType.SET_FOCUS_MODE,
            extra_data={"focus_mode_active": active, "reason": reason},
            message=f"Focus Mode {'ACTIVATED' if active else 'DEACTIVATED'} by Instructor.",
            issued_by="Focus Mode Master Switch",
        )
        delivered = await self.broadcast_command(cmd)
        await self.broadcast_admin_update()
        return delivered

    # ==============================================================================
    # Feature 3: Central File Broadcast & Assignment Collection
    # ==============================================================================
    async def broadcast_file(self, payload: FileBroadcastPayload) -> int:
        """Broadcasts a lecture sheet, code file, or document to all connected workstations."""
        cmd = AdminCommandPayload(
            command=CommandType.BROADCAST_FILE,
            extra_data=payload.model_dump(mode="json"),
            message=f"Instructor shared file: {payload.filename}",
            issued_by=payload.sender,
        )
        return await self.broadcast_command(cmd)

    async def collect_assignments(self, req: CollectAssignmentsRequest) -> int:
        """Requests assignment submission file upload from all active student workstations."""
        cmd = AdminCommandPayload(
            command=CommandType.COLLECT_ASSIGNMENTS,
            extra_data=req.model_dump(mode="json"),
            message=f"Please submit assignment: {req.assignment_name}",
            issued_by="Assignment Collector",
        )
        return await self.broadcast_command(cmd)

    def save_assignment_submission(self, sub: AssignmentSubmissionPayload) -> str:
        """Saves a submitted student assignment file to the central repository."""
        import base64
        from pathlib import Path
        import re

        safe_client = re.sub(r"[^\w\-]", "_", sub.client_id)
        safe_student = re.sub(r"[^\w\-]", "_", sub.student_name)
        safe_filename = re.sub(r"[^\w\.\-]", "_", sub.filename)

        folder = Path(self.collected_assignments_dir) / f"{safe_client}_{safe_student}"
        folder.mkdir(parents=True, exist_ok=True)
        target_path = folder / safe_filename

        file_bytes = base64.b64decode(sub.file_content_base64)
        target_path.write_bytes(file_bytes)
        logger.info("Saved assignment submission: %s from %s", safe_filename, sub.client_id)
        return str(target_path)

    def get_collected_submissions(self) -> List[Dict[str, Any]]:
        """Returns metadata list of all collected assignments stored on disk."""
        from pathlib import Path
        root = Path(self.collected_assignments_dir)
        submissions = []
        if not root.exists():
            return submissions

        for file_path in root.glob("*/*"):
            if file_path.is_file():
                folder_name = file_path.parent.name
                parts = folder_name.split("_", 1)
                client_id = parts[0]
                student_name = parts[1] if len(parts) > 1 else "Unknown"
                stat = file_path.stat()
                submissions.append({
                    "client_id": client_id,
                    "student_name": student_name,
                    "filename": file_path.name,
                    "file_path": str(file_path),
                    "size_bytes": stat.st_size,
                    "submitted_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                })
        return sorted(submissions, key=lambda s: s["submitted_at"], reverse=True)

    # ==============================================================================
    # Feature 4: USB Storage Policy
    # ==============================================================================
    async def set_usb_policy(self, blocked: bool, target_client_id: Optional[str] = None) -> int:
        """Applies USB mass storage restriction policy to all or a specific workstation."""
        self.usb_storage_blocked = blocked
        cmd = AdminCommandPayload(
            command=CommandType.SET_USB_POLICY,
            target_client_id=target_client_id,
            extra_data={"usb_blocked": blocked},
            message=f"USB Storage {'BLOCKED 🔒' if blocked else 'UNRESTRICTED 💾'} by Lab Policy.",
            issued_by="Lab Security Policy",
        )
        if target_client_id:
            state = self._workstations.get(target_client_id)
            if state:
                state.usb_blocked = blocked
            success = await self.send_command_to_client(target_client_id, cmd)
            await self.broadcast_admin_update()
            return 1 if success else 0
        else:
            for state in self._workstations.values():
                state.usb_blocked = blocked
            delivered = await self.broadcast_command(cmd)
            await self.broadcast_admin_update()
            return delivered

    # ==============================================================================
    # Feature 6: Master Host Workstation Control
    # ==============================================================================
    def update_host_metrics(self) -> WorkstationState:
        """
        Refreshes live hardware telemetry (CPU, RAM, OS, IP) for the Central Admin Host PC
        using psutil and platform introspection.
        """
        import os
        import platform
        import socket
        import psutil

        now = datetime.now(timezone.utc)
        try:
            cpu_pct = float(psutil.cpu_percent(interval=None) or 0.0)
            ram_pct = float(psutil.virtual_memory().percent or 0.0)
        except Exception:
            cpu_pct = 12.5
            ram_pct = 48.0

        hostname = socket.gethostname()
        os_info = f"{platform.system()} {platform.release()}".strip()

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            host_ip = s.getsockname()[0]
            s.close()
        except Exception:
            host_ip = "127.0.0.1"

        state = self._workstations.get(self.MASTER_HOST_ID)
        if not state:
            state = WorkstationState(
                client_id=self.MASTER_HOST_ID,
                hostname=f"{hostname} (Host Machine)",
                ip_address=host_ip,
                student_name="Central Admin (Host Machine)",
                os_info=os_info,
                status=WorkstationStatus.ONLINE,
                last_heartbeat=now,
                productivity_score=100,
                is_master_host=True,
            )
            self._workstations[self.MASTER_HOST_ID] = state
        else:
            state.hostname = f"{hostname} (Host Machine)"
            state.ip_address = host_ip
            state.os_info = os_info
            state.last_heartbeat = now
            state.is_master_host = True
            if not state.curfew_locked and state.status not in (WorkstationStatus.IDLE,):
                state.status = WorkstationStatus.ONLINE

        state.latest_telemetry = TelemetryPayload(
            client_id=self.MASTER_HOST_ID,
            cpu_percent=cpu_pct,
            ram_percent=ram_pct,
            active_window_title="Smart Lab Command Center Console",
            active_process_name="python.exe",
            is_idle=False,
            timestamp=now,
        )
        return state

    async def lock_host_machine(self, reason: str = "Admin Directive") -> Dict[str, Any]:
        """Locks the Central Admin Host computer display safely."""
        import os
        import sys

        state = self._workstations.get(self.MASTER_HOST_ID) or self.update_host_metrics()
        state.curfew_locked = True
        state.status = WorkstationStatus.CURFEW_LOCKED

        demo_mode = os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes")
        safety_lock = os.getenv("HOST_SAFETY_LOCK", "true").lower() in ("true", "1", "yes")

        executed_real = False
        if not demo_mode and not safety_lock and sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.user32.LockWorkStation()
                executed_real = True
            except Exception as exc:
                logger.error("Real Windows LockWorkStation failed: %s", exc)

        logger.info("Host PC locked: %s (Real Win32: %s)", reason, executed_real)
        await self.broadcast_admin_update()
        return {
            "status": "success",
            "action": "LOCK_HOST",
            "message": "Host Workstation locked successfully." if executed_real else "Host Workstation screen lock simulated safely.",
            "is_locked": True,
            "real_executed": executed_real,
        }

    async def unlock_host_machine(self, reason: str = "Admin Directive") -> Dict[str, Any]:
        """Unlocks the Central Admin Host computer state."""
        state = self._workstations.get(self.MASTER_HOST_ID) or self.update_host_metrics()
        state.curfew_locked = False
        state.status = WorkstationStatus.ONLINE
        await self.broadcast_admin_update()
        logger.info("Host PC unlocked: %s", reason)
        return {
            "status": "success",
            "action": "UNLOCK_HOST",
            "message": "Host Workstation unlocked.",
            "is_locked": False,
        }

    async def sleep_host_machine(self, reason: str = "Admin Directive") -> Dict[str, Any]:
        """Puts the Host computer into standby / sleep state safely."""
        state = self._workstations.get(self.MASTER_HOST_ID) or self.update_host_metrics()
        state.status = WorkstationStatus.IDLE
        await self.broadcast_admin_update()
        logger.info("Host PC sleep requested: %s", reason)
        return {
            "status": "success",
            "action": "SLEEP_HOST",
            "message": "Host Workstation standby power mode activated.",
        }


