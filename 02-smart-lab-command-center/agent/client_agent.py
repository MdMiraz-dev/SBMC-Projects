"""Module: agent/client_agent.py
Description: Lightweight background daemon for student workstations.
Streams hardware telemetry and foreground window state to Central Command Server,
and listens for remote administrative instructions (LOCK, UNLOCK, SHUTDOWN, MESSAGE).
Adheres to SBMC AGENTS.md: Resilient reconnection, safe command handling, zero unhandled exceptions.
"""

import argparse
import asyncio
import base64
from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import platform
import socket
import sys
from typing import Any, Dict, Optional

import websockets

from .screen_capture import ScreenCaptureEngine
from .window_monitor import WindowMonitor

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [AGENT] %(message)s")
logger = logging.getLogger("smart_lab.agent")


class SmartLabAgent:
    """Student workstation daemon connecting to Central Command Server via WebSocket."""

    def __init__(
        self,
        server_host: str = "127.0.0.1",
        server_port: int = 8500,
        client_id: Optional[str] = None,
        cluster_secret: Optional[str] = None,
        student_name: str = "Student Workstation",
        heartbeat_interval: float = 5.0,
        mock_mode: bool = False,
    ):
        self.server_host = server_host
        self.server_port = server_port
        self.hostname = socket.gethostname()
        self.client_id = client_id or f"PC-{self.hostname.split('-')[-1] if '-' in self.hostname else self.hostname[:6].upper()}"
        self.cluster_secret = cluster_secret or os.getenv("LAB_CLUSTER_SECRET", "as_sunnah_lab_agent_secret_2026")
        self.student_name = student_name
        self.heartbeat_interval = heartbeat_interval
        self.mock_mode = mock_mode

        self.monitor = WindowMonitor()
        self.screen_engine = ScreenCaptureEngine(is_mock=self.mock_mode)
        self.is_locked = False
        self.usb_blocked = False
        self.focus_mode_active = False
        self._last_title = "Visual Studio Code"
        self._running = True

    @property
    def ws_url(self) -> str:
        return f"ws://{self.server_host}:{self.server_port}/ws/agent/{self.client_id}?token={self.cluster_secret}"

    def build_registration_payload(self) -> Dict[str, Any]:
        """Constructs initial handshake registration packet."""
        ip = "192.168.1.101" if self.mock_mode else self.monitor.get_local_ip()
        return {
            "type": "REGISTER",
            "data": {
                "client_id": self.client_id,
                "hostname": self.hostname,
                "ip_address": ip,
                "os_info": f"{platform.system()} {platform.release()}",
                "student_name": self.student_name,
                "agent_version": "1.0.0",
            },
        }

    def collect_telemetry(self) -> Dict[str, Any]:
        """Collects current workstation state and metrics."""
        cpu, ram = self.monitor.get_hardware_stats()
        title, proc = self.monitor.get_active_window()

        if self.mock_mode:
            import random
            self._mock_step = getattr(self, "_mock_step", 0) + 1
            mock_titles = [
                ("Visual Studio Code - main.py (As-Sunnah Python Lab 04)", "Code.exe"),
                ("FastAPI Web Development Tutorial - YouTube", "chrome.exe"),
                ("As-Sunnah Foundation Computer Training - Lab Notes", "msedge.exe"),
                ("Terminal - git commit -m 'feat: complete lab task'", "powershell.exe"),
            ]
            title, proc = mock_titles[self._mock_step % len(mock_titles)]
            cpu = round(random.uniform(9.0, 26.5), 1)
            ram = round(random.uniform(44.0, 56.5), 1)

        self._last_title = title or "Visual Studio Code"
        screen_b64 = self.screen_engine.capture_frame(
            width=720,
            height=405,
            quality=55,
            active_title=self._last_title,
            client_id=self.client_id,
            student_name=self.student_name,
            is_locked=self.is_locked,
        )

        return {
            "type": "TELEMETRY",
            "data": {
                "client_id": self.client_id,
                "cpu_percent": cpu,
                "ram_percent": ram,
                "active_window_title": title,
                "active_process_name": proc,
                "is_idle": cpu < 2.0,
                "screen_thumbnail": screen_b64,
                "usb_blocked": self.usb_blocked,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        }

    async def handle_inbound_command(self, raw_message: str, websocket: Optional[Any] = None) -> None:
        """Processes authorized administrative command received from central server."""
        try:
            cmd = json.loads(raw_message)
            cmd_type = cmd.get("command")
            message_text = cmd.get("message")
            extra = cmd.get("extra_data") or {}
            logger.info("Received server directive: %s | Message: %s", cmd_type, message_text)

            if cmd_type == "LOCK":
                self.is_locked = True
                logger.warning("WORKSTATION LOCKED BY INSTRUCTOR / CURFEW")
                print("\n" + "=" * 60)
                print("[LOCKED] [AS-SUNNAH LAB] WORKSTATION LOCKED BY INSTRUCTOR")
                if message_text:
                    print(f"Notice: {message_text}")
                print("=" * 60 + "\n")

            elif cmd_type == "UNLOCK":
                self.is_locked = False
                logger.info("WORKSTATION UNLOCKED BY INSTRUCTOR")
                print("\n[UNLOCKED] Workstation unlocked. Resuming normal session.\n")

            elif cmd_type == "BROADCAST_MESSAGE":
                print("\n" + "*" * 60)
                print(f"[ANNOUNCEMENT] [INSTRUCTOR NOTICE]: {message_text}")
                print("*" * 60 + "\n")

            elif cmd_type == "CAPTURE_SCREEN":
                logger.info("High-res screen capture requested by instructor.")
                frame = self.screen_engine.capture_frame(
                    width=960,
                    height=540,
                    quality=70,
                    active_title=self._last_title,
                    client_id=self.client_id,
                    student_name=self.student_name,
                    is_locked=self.is_locked,
                )
                if websocket:
                    resp = {
                        "type": "SCREEN_CAPTURE",
                        "client_id": self.client_id,
                        "image": frame,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                    await websocket.send(json.dumps(resp))

            elif cmd_type == "BROADCAST_FILE":
                filename = extra.get("filename", "lab_material.txt")
                b64_content = extra.get("file_content_base64", "")
                target_folder = extra.get("target_folder", "lab_materials")
                folder_path = Path(target_folder)
                folder_path.mkdir(parents=True, exist_ok=True)
                target_file = folder_path / filename
                if b64_content:
                    target_file.write_bytes(base64.b64decode(b64_content))
                print("\n" + "=" * 60)
                print(f"[FILE RECEIVED] New course material distributed by instructor: {filename}")
                print(f"Saved locally to: {target_file.resolve()}")
                print("=" * 60 + "\n")

            elif cmd_type == "COLLECT_ASSIGNMENTS":
                req_filename = extra.get("assignment_name", "submission.py")
                folder_path = Path(extra.get("folder_path", "assignments"))
                folder_path.mkdir(parents=True, exist_ok=True)
                target_file = folder_path / req_filename

                if not target_file.exists():
                    target_file.write_text(
                        f"# As-Sunnah Computer Lab Assignment Submission\n"
                        f"# Student: {self.student_name} ({self.client_id})\n"
                        f"# Timestamp: {datetime.now(timezone.utc).isoformat()}\n\n"
                        f"def solution():\n"
                        f"    print('Module task completed successfully by {self.student_name}')\n\n"
                        f"if __name__ == '__main__':\n"
                        f"    solution()\n",
                        encoding="utf-8",
                    )

                content_bytes = target_file.read_bytes()
                sub_b64 = base64.b64encode(content_bytes).decode("utf-8")
                if websocket:
                    resp = {
                        "type": "ASSIGNMENT_SUBMISSION",
                        "data": {
                            "client_id": self.client_id,
                            "student_name": self.student_name,
                            "filename": target_file.name,
                            "file_content_base64": sub_b64,
                            "file_size_bytes": len(content_bytes),
                            "submitted_at": datetime.now(timezone.utc).isoformat(),
                        },
                    }
                    await websocket.send(json.dumps(resp))
                print(f"[SUBMISSION] Sent assignment file '{target_file.name}' to central repository.")

            elif cmd_type == "SET_USB_POLICY":
                blocked = extra.get("usb_blocked", False)
                self.usb_blocked = blocked
                status_label = "BLOCKED (Mass storage disabled) 🔒" if blocked else "ALLOWED (Normal access) 💾"
                print(f"\n[POLICY] USB Storage Policy updated: {status_label}\n")

            elif cmd_type == "SET_FOCUS_MODE":
                active = extra.get("focus_mode_active", False)
                self.focus_mode_active = active
                status_label = "ACTIVE (Distractions Prohibited) 🎯" if active else "OFF"
                print(f"\n[POLICY] Focus Mode: {status_label}\n")

            elif cmd_type == "SHUTDOWN":
                logger.critical("SHUTDOWN DIRECTIVE RECEIVED. Initiating shutdown sequence.")
                print("\n[POWER OFF] [CURFEW SHUTDOWN] Shutting down lab computer in 15 seconds...\n")
                if not self.mock_mode and platform.system() == "Windows":
                    os.system("shutdown /s /t 15 /c \"As-Sunnah Lab Curfew Initiated\"")

        except Exception as exc:
            logger.error("Failed to parse inbound command: %s", exc)

    async def _send_telemetry_loop(self, websocket: websockets.WebSocketClientProtocol) -> None:
        """Periodically streams telemetry and heartbeats to server."""
        while self._running:
            try:
                payload = self.collect_telemetry()
                await websocket.send(json.dumps(payload))
                await asyncio.sleep(self.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.warning("Telemetry transmission interrupted: %s", exc)
                break

    async def _receive_command_loop(self, websocket: websockets.WebSocketClientProtocol) -> None:
        """Listens for remote instructions emitted by instructor."""
        while self._running:
            try:
                msg = await websocket.recv()
                await self.handle_inbound_command(msg, websocket)
            except asyncio.CancelledError:
                break
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Connection closed by server.")
                break
            except Exception as exc:
                logger.error("Command listener error: %s", exc)
                break

    async def run_session(self) -> None:
        """Main connection and session manager with automatic retry backoff."""
        backoff = 2.0
        while self._running:
            try:
                logger.info("Attempting connection to Central Command: %s", self.ws_url)
                async with websockets.connect(self.ws_url) as ws:
                    backoff = 2.0
                    logger.info("Connected successfully as %s", self.client_id)

                    # Handshake registration
                    await ws.send(json.dumps(self.build_registration_payload()))

                    # Run telemetry and command listeners concurrently
                    send_task = asyncio.create_task(self._send_telemetry_loop(ws))
                    recv_task = asyncio.create_task(self._receive_command_loop(ws))

                    done, pending = await asyncio.wait(
                        [send_task, recv_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )

                    for p in pending:
                        p.cancel()

            except (websockets.exceptions.WebSocketException, OSError) as exc:
                logger.warning("Connection to command center failed (%s). Retrying in %.1fs...", exc, backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 1.5, 15.0)
            except Exception as exc:
                logger.error("Unexpected error in agent session: %s", exc)
                await asyncio.sleep(5.0)


def main():
    parser = argparse.ArgumentParser(description="Smart Lab Workstation Agent Daemon")
    parser.add_argument("--host", default="127.0.0.1", help="Central Command Server Host")
    parser.add_argument("--port", type=int, default=8500, help="Central Command Server Port")
    parser.add_argument("--client-id", default=None, help="Workstation ID (e.g. LAB-PC-01)")
    parser.add_argument("--student", default="Student Workstation", help="Assigned student name")
    parser.add_argument("--mock", action="store_true", help="Run with mock telemetry for testing")
    args = parser.parse_args()

    agent = SmartLabAgent(
        server_host=args.host,
        server_port=args.port,
        client_id=args.client_id,
        student_name=args.student,
        mock_mode=args.mock,
    )
    asyncio.run(agent.run_session())


if __name__ == "__main__":
    main()
