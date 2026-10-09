"""Module: agent/window_monitor.py
Description: Cross-platform telemetry collector for student workstation.
Extracts active foreground window title, process name, and hardware metrics.
Adheres to AGENTS.md: Safe cross-platform fallback, non-crashing telemetry extraction.
"""

import os
import platform
import socket
from typing import Optional, Tuple
import psutil


class WindowMonitor:
    """Collects operating system telemetry and active foreground application state."""

    def __init__(self):
        self.is_windows = platform.system() == "Windows"
        self._user32 = None
        if self.is_windows:
            try:
                import ctypes
                self._user32 = ctypes.windll.user32
            except Exception:
                self._user32 = None

    def get_local_ip(self) -> str:
        """Determines active local LAN IPv4 address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            # Dummy connection to determine preferred outbound network interface
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return "127.0.0.1"

    def get_active_window(self) -> Tuple[str, str]:
        """
        Returns (active_window_title, active_process_name).
        Gracefully handles non-GUI headless environments, Linux, and Windows.
        """
        if self.is_windows and self._user32:
            try:
                import ctypes
                hwnd = self._user32.GetForegroundWindow()
                if not hwnd:
                    return ("", "")

                # Retrieve window text
                length = self._user32.GetWindowTextLengthW(hwnd)
                buff = ctypes.create_unicode_buffer(length + 1)
                self._user32.GetWindowTextW(hwnd, buff, length + 1)
                title = buff.value.strip()

                # Retrieve Process ID
                pid = ctypes.c_ulong()
                self._user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                proc_name = ""
                try:
                    proc = psutil.Process(pid.value)
                    proc_name = proc.name()
                except Exception:
                    pass

                return (title, proc_name)
            except Exception:
                return ("", "")

        # Fallback for headless environments or non-Windows systems
        return ("", "")

    def get_hardware_stats(self) -> Tuple[float, float]:
        """Returns (cpu_percent, ram_percent) bounded between 0.0 and 100.0."""
        try:
            cpu = float(psutil.cpu_percent(interval=None))
            ram = float(psutil.virtual_memory().percent)
            return (min(100.0, max(0.0, cpu)), min(100.0, max(0.0, ram)))
        except Exception:
            return (0.0, 0.0)
