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
    ClientRegistration,
    DistractionCategory,
    TamperAlertEvent,
    TelemetryPayload,
    WorkstationState,
    WorkstationStatus,
)

logger = logging.getLogger("smart_lab.manager")


class LabConnectionManager:
    """Manages active WebSocket sessions from student PCs and instructor dashboards."""

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

    def get_all_workstations(self) -> List[WorkstationState]:
        """Returns snapshot list of all registered workstations sorted by client_id."""
        return sorted(self._workstations.values(), key=lambda w: w.client_id)

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

        # Distraction Heuristic Evaluation
        report = self.detector.evaluate(
            active_window_title=telemetry.active_window_title,
            active_process_name=telemetry.active_process_name,
        )
        state.distraction_report = report

        if report.is_distracted:
            state.status = WorkstationStatus.DISTRACTED
            state.violation_count += 1
        elif state.curfew_locked:
            state.status = WorkstationStatus.CURFEW_LOCKED
        elif telemetry.is_idle:
            state.status = WorkstationStatus.IDLE
        else:
            state.status = WorkstationStatus.ONLINE

        await self.broadcast_admin_update()
        return state

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

        payload = {
            "type": "CLUSTER_UPDATE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_registered": len(self._workstations),
            "total_online": sum(1 for w in self._workstations.values() if w.status == WorkstationStatus.ONLINE),
            "total_distracted": sum(1 for w in self._workstations.values() if w.status == WorkstationStatus.DISTRACTED),
            "total_tampered": sum(1 for w in self._workstations.values() if w.status == WorkstationStatus.DISCONNECTED_TAMPERED),
            "workstations": [w.model_dump(mode="json") for w in self.get_all_workstations()],
            "alerts": [a.model_dump(mode="json") for a in self.get_active_alerts()],
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
