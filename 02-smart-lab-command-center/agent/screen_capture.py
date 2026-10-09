"""Module: agent/screen_capture.py
Description: Safe, lightweight screen capture engine for student workstations.
Supports both live OS screen grabbing and high-fidelity mock desktop generation.
Adheres to AGENTS.md: Non-blocking, safe memory buffer handling, zero-leak JPEG encoding.
"""

import base64
from datetime import datetime, timezone
import io
import platform
from typing import Optional, Tuple

from PIL import Image, ImageDraw, ImageFont


class ScreenCaptureEngine:
    """Captures workstation screen or produces simulated high-fidelity lab desktops."""

    def __init__(self, is_mock: bool = False):
        self.is_mock = is_mock
        self.is_windows = platform.system() == "Windows"

    def capture_frame(
        self,
        width: int = 800,
        height: int = 450,
        quality: int = 60,
        active_title: str = "Visual Studio Code - Python Lab",
        client_id: str = "LAB-PC-01",
        student_name: str = "Student Workstation",
        is_locked: bool = False,
    ) -> str:
        """
        Captures the screen and returns a base64-encoded JPEG Data URI string.
        Falls back to generating a realistic synthetic desktop if in mock mode or headless.
        """
        if not self.is_mock and self.is_windows:
            try:
                from PIL import ImageGrab
                img = ImageGrab.grab()
                if img:
                    img = img.resize((width, height), Image.Resampling.BILINEAR)
                    buf = io.BytesIO()
                    img.convert("RGB").save(buf, format="JPEG", quality=quality, optimize=True)
                    raw_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
                    return f"data:image/jpeg;base64,{raw_b64}"
            except Exception:
                # Fall back to synthetic mock desktop
                pass

        return self.generate_mock_screen(
            width=width,
            height=height,
            quality=quality,
            active_title=active_title,
            client_id=client_id,
            student_name=student_name,
            is_locked=is_locked,
        )

    def generate_mock_screen(
        self,
        width: int = 800,
        height: int = 450,
        quality: int = 60,
        active_title: str = "Visual Studio Code - Python Lab",
        client_id: str = "LAB-PC-01",
        student_name: str = "Student Workstation",
        is_locked: bool = False,
    ) -> str:
        """
        Generates a synthetic, high-fidelity student desktop preview image with code editor,
        terminal, taskbar, and As-Sunnah lab branding.
        """
        # Create base canvas (Dark sleek background)
        img = Image.new("RGB", (width, height), color=(15, 23, 42))  # slate-900
        draw = ImageDraw.Draw(img)

        # If Curfew Locked
        if is_locked:
            # Curfew lock full screen overlay
            draw.rectangle([0, 0, width, height], fill=(24, 16, 48))
            draw.rectangle([width // 6, height // 5, 5 * width // 6, 4 * height // 5], fill=(30, 20, 60), outline=(147, 51, 234), width=3)
            draw.text((width // 4, height // 3), "AS-SUNNAH COMPUTER LAB — CURFEW LOCK", fill=(255, 255, 255))
            draw.text((width // 4, height // 3 + 40), f"Workstation {client_id} locked by lab administration.", fill=(216, 180, 254))
            draw.text((width // 4, height // 3 + 80), "Please prepare to exit the laboratory.", fill=(168, 85, 247))
        else:
            # 1. Wallpaper Accent Gradient Box
            draw.rectangle([0, 0, width, height - 32], fill=(15, 23, 42))
            draw.ellipse([width - 300, -100, width + 100, 300], fill=(24, 34, 65))

            # 2. Main Active Application Window (e.g. VS Code or Browser)
            app_left, app_top, app_right, app_bottom = 40, 30, width - 40, height - 55
            # Window shadow & border
            draw.rectangle([app_left - 1, app_top - 1, app_right + 1, app_bottom + 1], fill=(30, 41, 59), outline=(71, 85, 105), width=2)
            # Window Titlebar
            draw.rectangle([app_left, app_top, app_right, app_top + 26], fill=(30, 41, 59))
            # Window Control dots (mac/modern style)
            draw.ellipse([app_left + 10, app_top + 8, app_left + 18, app_top + 16], fill=(239, 68, 68))
            draw.ellipse([app_left + 24, app_top + 8, app_left + 32, app_top + 16], fill=(234, 179, 8))
            draw.ellipse([app_left + 38, app_top + 8, app_left + 46, app_top + 16], fill=(34, 197, 94))
            # Window Title text
            draw.text((app_left + 55, app_top + 6), active_title[:65], fill=(226, 232, 240))

            # Window Interior (Editor Canvas)
            draw.rectangle([app_left, app_top + 27, app_right, app_bottom], fill=(15, 20, 32))

            # Left Sidebar / Activity Bar
            draw.rectangle([app_left, app_top + 27, app_left + 40, app_bottom], fill=(20, 27, 45))
            draw.rectangle([app_left + 8, app_top + 38, app_left + 32, app_top + 42], fill=(99, 102, 241))
            draw.rectangle([app_left + 8, app_top + 50, app_left + 32, app_top + 54], fill=(148, 163, 184))

            # Synthetic Code Editor lines
            code_snippets = [
                ("from fastapi import FastAPI, WebSocket", (192, 132, 252)),
                ("from automation import LeadAutomationService", (129, 140, 248)),
                ("", (0, 0, 0)),
                ("app = FastAPI(title='As-Sunnah Smart Lab Engine')", (52, 211, 153)),
                ("@app.websocket('/ws/telemetry')", (251, 191, 36)),
                ("async def telemetry_stream(ws: WebSocket):", (96, 165, 250)),
                ("    await ws.accept()", (203, 213, 225)),
                ("    print('Workstation telemetry synchronized.')", (244, 114, 182)),
            ]
            y_offset = app_top + 40
            for line_idx, (text, color) in enumerate(code_snippets):
                # Line numbers
                draw.text((app_left + 48, y_offset), f"{line_idx + 1:2d}", fill=(71, 85, 105))
                # Line code
                if text:
                    draw.text((app_left + 75, y_offset), text, fill=color)
                y_offset += 18

            # Mini Terminal Panel at bottom of Editor
            term_top = app_bottom - 75
            draw.rectangle([app_left + 40, term_top, app_right, app_bottom], fill=(10, 15, 26), outline=(51, 65, 85), width=1)
            draw.text((app_left + 48, term_top + 6), f"TERMINAL — PowerShell (Host: {client_id})", fill=(148, 163, 184))
            draw.text((app_left + 48, term_top + 24), "PS C:\\As-Sunnah\\Labs> python -m test_automation", fill=(52, 211, 153))
            draw.text((app_left + 48, term_top + 42), "================ 50 passed in 1.45s ================", fill=(34, 197, 94))

            # 3. Bottom Taskbar
            draw.rectangle([0, height - 32, width, height], fill=(10, 15, 28), outline=(30, 41, 59), width=1)
            # Start button
            draw.rectangle([12, height - 26, 36, height - 6], fill=(59, 130, 246), outline=(96, 165, 250), width=1)
            draw.rectangle([44, height - 26, 68, height - 6], fill=(30, 41, 59))
            draw.rectangle([76, height - 26, 100, height - 6], fill=(30, 41, 59))

            # Taskbar Right Clock & Student Tag
            now_str = datetime.now().strftime("%H:%M:%S")
            draw.text((width - 90, height - 22), now_str, fill=(226, 232, 240))
            draw.text((width - 270, height - 22), f"Student: {student_name[:18]}", fill=(148, 163, 184))

        # Watermark Stamp
        draw.text((width - 240, 10), f"VEYON LIVE STREAM • {client_id}", fill=(100, 116, 139))

        # Buffer export
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        raw_b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{raw_b64}"
