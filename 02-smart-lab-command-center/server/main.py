"""Module: server/main.py
Description: FastAPI Central Server for Smart Lab Command Center.
Provides WebSocket endpoints for workstation agents and instructor dashboard,
curfew policy enforcement, tamper detection watchdog, and REST management APIs.
Adheres to SBMC AGENTS.md: Strict typing, async concurrency, clean separation of concerns.
"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query, Request, Response, WebSocket, WebSocketDisconnect, status
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

from .curfew import CurfewDecision, CurfewEngine, CurfewStage
from .detector import DistractionDetector
from .manager import LabConnectionManager
from .schemas import (
    AdminCommandPayload,
    ClientRegistration,
    CommandType,
    CurfewConfig,
    TelemetryPayload,
    WorkstationState,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("smart_lab.server")

# Security and Network Configuration
SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8500"))
LAB_CLUSTER_SECRET: str = os.getenv("LAB_CLUSTER_SECRET", "as_sunnah_lab_agent_secret_2026")
ADMIN_SECRET_KEY: str = os.getenv("ADMIN_SECRET_KEY", "sbmc_smart_lab_admin_token_2026")
HEARTBEAT_TIMEOUT_SECONDS: float = float(os.getenv("HEARTBEAT_TIMEOUT_SECONDS", "15.0"))
CURFEW_ENABLED: bool = os.getenv("CURFEW_ENABLED", "true").lower() in ("true", "1", "yes")
DEMO_MODE: bool = os.getenv("DEMO_MODE", "false").lower() in ("true", "1", "yes")

# Core Singletons
detector = DistractionDetector()
manager = LabConnectionManager(detector=detector)
curfew_engine = CurfewEngine(config=CurfewConfig(enabled=CURFEW_ENABLED))
if DEMO_MODE:
    curfew_engine.set_override(True, "Live Demo Session (Curfew Override Active)")

# Background Watchdog Tasks
_watchdog_tasks: List[asyncio.Task] = []


async def _heartbeat_watchdog_loop() -> None:
    """Periodically inspects workstations for dropped heartbeats to catch tampering."""
    while True:
        try:
            await asyncio.sleep(4.0)
            await manager.check_heartbeat_timeouts(timeout_seconds=HEARTBEAT_TIMEOUT_SECONDS)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Error in heartbeat watchdog: %s", exc)


async def _curfew_scheduler_loop() -> None:
    """Monitors lab hours and executes 20:50 warnings, 21:00 screen locks, and 21:05 shutdowns."""
    last_executed_stage: Optional[CurfewStage] = None

    while True:
        try:
            await asyncio.sleep(10.0)
            decision = curfew_engine.evaluate()

            if decision.action_required and decision.suggested_command:
                # Trigger action only upon transition into that stage
                if decision.stage != last_executed_stage:
                    last_executed_stage = decision.stage
                    logger.warning("Curfew event triggered: %s (%s)", decision.stage.value, decision.reason)
                    cmd = AdminCommandPayload(
                        command=decision.suggested_command,
                        message=decision.broadcast_message,
                        issued_by="Curfew Policy Engine",
                    )
                    await manager.broadcast_command(cmd)
            elif decision.stage == CurfewStage.NORMAL:
                last_executed_stage = None
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error("Error in curfew scheduler: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes background monitors upon application startup and gracefully cancels on exit."""
    logger.info("Initializing Smart Lab Command Center background watchdogs...")
    hb_task = asyncio.create_task(_heartbeat_watchdog_loop())
    curfew_task = asyncio.create_task(_curfew_scheduler_loop())
    tasks = [hb_task, curfew_task]
    try:
        yield
    finally:
        logger.info("Shutting down background watchdogs...")
        for t in tasks:
            t.cancel()
        for t in tasks:
            try:
                await t
            except (asyncio.CancelledError, Exception):
                pass


app = FastAPI(
    title="Smart Lab Command Center",
    description="Centralized Workstation Management, Distraction Detection, and Curfew System for As-Sunnah Labs",
    version="1.0.0",
    lifespan=lifespan,
)


# ==============================================================================
# Instructor Command Dashboard Web Route
# ==============================================================================

@app.get("/", response_class=HTMLResponse)
@app.get("/dashboard", response_class=HTMLResponse)
async def serve_dashboard():
    """Serves the live interactive instructor command dashboard."""
    template_path = Path(__file__).parent / "templates" / "dashboard.html"
    if not template_path.exists():
        raise HTTPException(status_code=500, detail="Dashboard template missing.")
    return HTMLResponse(content=template_path.read_text(encoding="utf-8"))


# ==============================================================================
# WebSocket Endpoints
# ==============================================================================

@app.websocket("/ws/agent/{client_id}")
async def workstation_agent_socket(
    websocket: WebSocket,
    client_id: str,
    token: Optional[str] = Query(None),
):
    """
    WebSocket connection endpoint for student workstation background agents.
    Enforces cluster secret authentication and handles continuous telemetry stream.
    """
    # 1. Cluster Secret Handshake Validation
    if token != LAB_CLUSTER_SECRET:
        logger.warning("Agent %s attempted connection with invalid cluster token.", client_id)
        await websocket.close(code=4401, reason="Invalid cluster secret token.")
        return

    registered_client_id: Optional[str] = None

    try:
        # 2. Wait for initial ClientRegistration payload
        await websocket.accept()
        init_raw = await websocket.receive_text()
        init_json = json.loads(init_raw)

        if init_json.get("type") != "REGISTER":
            await websocket.close(code=4400, reason="Initial message must be REGISTER.")
            return

        registration = ClientRegistration.model_validate(init_json.get("data", {}))
        registered_client_id = registration.client_id

        # Register in manager (reuses accepted socket)
        manager._active_sockets[registered_client_id] = websocket
        now = datetime.now(timezone.utc)
        existing = manager._workstations.get(registered_client_id)
        if existing:
            existing.hostname = registration.hostname
            existing.ip_address = registration.ip_address
            existing.student_name = registration.student_name
            existing.os_info = registration.os_info
            existing.status = WorkstationState.model_fields["status"].default
            existing.last_heartbeat = now
        else:
            manager._workstations[registered_client_id] = WorkstationState(
                client_id=registered_client_id,
                hostname=registration.hostname,
                ip_address=registration.ip_address,
                student_name=registration.student_name,
                os_info=registration.os_info,
                last_heartbeat=now,
            )

        await manager.broadcast_admin_update()
        logger.info("Agent %s registered successfully from %s", registered_client_id, registration.ip_address)

        # 3. Continuous Telemetry Ingestion Loop
        while True:
            msg_text = await websocket.receive_text()
            msg_json = json.loads(msg_text)
            msg_type = msg_json.get("type")

            if msg_type == "TELEMETRY":
                telemetry = TelemetryPayload.model_validate(msg_json.get("data", {}))
                await manager.record_telemetry(telemetry)
            elif msg_type == "SCREEN_CAPTURE":
                img_data = msg_json.get("image")
                if img_data:
                    st = manager.get_workstation(registered_client_id)
                    if st:
                        st.screen_thumbnail = img_data
                        await manager.broadcast_admin_update()
            elif msg_type == "HEARTBEAT":
                st = manager.get_workstation(registered_client_id)
                if st:
                    st.last_heartbeat = datetime.now(timezone.utc)
            else:
                logger.debug("Unknown message type from %s: %s", registered_client_id, msg_type)

    except WebSocketDisconnect:
        logger.info("Agent disconnected: %s", registered_client_id or client_id)
        if registered_client_id:
            await manager.handle_disconnect(registered_client_id)
    except Exception as exc:
        logger.error("Error in agent socket %s: %s", client_id, exc)
        if registered_client_id:
            await manager.handle_disconnect(registered_client_id)


@app.websocket("/ws/admin")
async def admin_dashboard_socket(websocket: WebSocket):
    """Live streaming WebSocket connection feeding real-time updates to instructor dashboard."""
    await manager.register_admin_socket(websocket)
    try:
        while True:
            # Keep alive and receive instructor ping/actions if sent
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.unregister_admin_socket(websocket)
    except Exception:
        manager.unregister_admin_socket(websocket)


# ==============================================================================
# Admin REST Management Endpoints
# ==============================================================================

class BroadcastRequest(BaseModel):
    command: CommandType
    message: Optional[str] = None
    target_process: Optional[str] = None


class OverrideRequest(BaseModel):
    active: bool
    reason: Optional[str] = "Manual instructor override"


@app.get("/api/admin/workstations")
async def list_workstations() -> List[Dict[str, Any]]:
    """Returns all registered workstation states."""
    return [w.model_dump(mode="json") for w in manager.get_all_workstations()]


@app.get("/api/admin/screen/{client_id}")
async def get_workstation_screen(client_id: str):
    """Returns the latest live screen capture thumbnail for the workstation."""
    st = manager.get_workstation(client_id)
    if not st:
        raise HTTPException(status_code=404, detail="Workstation not found.")

    # Request fresh frame over WebSocket if connected
    cmd = AdminCommandPayload(
        command=CommandType.CAPTURE_SCREEN,
        target_client_id=client_id,
        issued_by="Instructor Screen View",
    )
    await manager.send_command_to_client(client_id, cmd)

    return {
        "client_id": client_id,
        "student_name": st.student_name,
        "active_title": st.latest_telemetry.active_window_title if st.latest_telemetry else "",
        "status": st.status.value,
        "image": st.screen_thumbnail,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/admin/alerts")
async def list_alerts() -> List[Dict[str, Any]]:
    """Returns active unacknowledged tamper alerts."""
    return [a.model_dump(mode="json") for a in manager.get_active_alerts()]


@app.post("/api/admin/alerts/ack/{alert_id}")
async def acknowledge_tamper_alert(alert_id: str):
    """Marks a tamper alert as acknowledged."""
    success = manager.acknowledge_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found.")
    await manager.broadcast_admin_update()
    return {"status": "success", "alert_id": alert_id}


@app.post("/api/admin/command/broadcast")
async def broadcast_command_to_all(payload: BroadcastRequest):
    """Dispatches a command (LOCK, UNLOCK, SHUTDOWN, MESSAGE) to all active workstations."""
    cmd = AdminCommandPayload(
        command=payload.command,
        message=payload.message,
        target_process=payload.target_process,
        issued_by="Lab Instructor",
    )
    dispatched = await manager.broadcast_command(cmd)
    return {
        "status": "success",
        "command": payload.command.value,
        "dispatched_count": dispatched,
    }


@app.post("/api/admin/command/client/{client_id}")
async def send_client_command(client_id: str, payload: BroadcastRequest):
    """Dispatches a command directly to an individual workstation."""
    cmd = AdminCommandPayload(
        command=payload.command,
        target_client_id=client_id,
        message=payload.message,
        target_process=payload.target_process,
        issued_by="Lab Instructor",
    )
    success = await manager.send_command_to_client(client_id, cmd)
    return {
        "status": "success" if success else "failed",
        "client_id": client_id,
        "success": success,
        "message": "Command delivered to agent." if success else "Workstation agent offline or unreachable.",
    }


@app.get("/api/admin/curfew/status")
async def get_curfew_status():
    """Returns current curfew timetable and evaluation state."""
    decision = curfew_engine.evaluate()
    return {
        "config": curfew_engine.config.model_dump(),
        "current_stage": decision.stage.value,
        "action_required": decision.action_required,
        "reason": decision.reason,
    }


@app.post("/api/admin/curfew/override")
async def set_curfew_override(payload: OverrideRequest):
    """Sets or clears instructor curfew override."""
    curfew_engine.set_override(payload.active, payload.reason or "Instructor override")
    await manager.broadcast_admin_update()
    return {
        "status": "success",
        "override_active": curfew_engine.config.override_active,
        "reason": curfew_engine.config.override_reason,
    }
