# Smart Lab Command Center (`02-smart-lab-command-center`)

> **Dedicated Educational Computer Lab Monitoring & Automated Curfew Enforcer**  
> Designed for **As-Sunnah Foundation Computer Labs** & modern technical training institutes.  
> Standardized under **SBMC AGENTS.md** engineering harness (Python 3.12+, FastAPI, WebSockets, Strict Pydantic Contracts).

---

## 1. Project Overview

The **Smart Lab Command Center** solves four critical operational problems in modern computer training centers:
1. **Focus & Distraction Management**: Detects social media portals, gaming, and short-form video addictions (**Facebook Reels**, **YouTube Shorts**, **TikTok**) while distinguishing and allowing educational lectures and tutorials.
2. **Resource Conservation & 9:00 PM Curfew**: Automatically enforces a standardized closing schedule:
   - **20:50 (10-minute warning)**: Broadcast warning notification.
   - **20:58 (2-minute warning)**: Final save reminder.
   - **21:00 (Curfew Lock)**: Screen lock across all lab computers with maintenance overlay.
   - **21:05 (Auto-Shutdown)**: Graceful automated OS power-off preventing idle power waste.
   - **Instructor Override**: Allows one-click extension for exams or overtime coding labs.
3. **Anti-Tampering Watchdog**: Tracks workstation heartbeats over low-latency WebSockets. If a student disconnects the Ethernet cable, turns off Wi-Fi, or terminates the agent task, an instant tamper alert (`DISCONNECTED_TAMPERED`) flashes on the instructor console.
4. **Live Workstation Grid**: Centralized single-pane-of-glass instructor dashboard showing all PCs, hardware metrics (CPU/RAM), active foreground windows, and one-click broadcast controls.

---

## 2. Directory Structure

```text
02-smart-lab-command-center/
├── spec.md                  # Comprehensive Architectural Specification
├── README.md                # Quick-start manual & operational documentation
├── .env.example             # Configuration and secret keys template
├── requirements.txt         # Pinned runtime dependencies
├── server/
│   ├── __init__.py
│   ├── main.py              # FastAPI server, WebSocket routing & REST endpoints
│   ├── schemas.py           # Strictly typed Pydantic models & validation rules
│   ├── manager.py           # Workstation connection manager & tamper watchdog
│   ├── curfew.py            # 21:00 Curfew policy engine & scheduler
│   ├── detector.py          # Distraction & Reels/Shorts heuristic engine
│   └── templates/
│       └── dashboard.html   # Tailwind CSS instructor real-time command dashboard
├── agent/
│   ├── __init__.py
│   ├── client_agent.py      # Student workstation background daemon
│   └── window_monitor.py    # Cross-platform telemetry & active window inspector
└── tests/
    ├── __init__.py
    ├── test_schemas.py      # Schema contract and boundary negative tests
    ├── test_detector.py     # Distraction heuristics & false positive tests
    ├── test_curfew.py       # 21:00 curfew boundary and override tests
    ├── test_manager.py      # Connection manager & heartbeat tamper tests
    └── test_integration.py  # End-to-end FastAPI endpoint integration tests
```

---

## 3. Quick Start & Execution

### 3.1 Install Dependencies
Make sure you are in the project virtual environment (`.venv`):
```powershell
pip install -r requirements.txt
```

### 3.2 Start Central Command Server
Run the FastAPI central server on port `8500` (listening on all local network interfaces):
```powershell
cd 02-smart-lab-command-center
python -m uvicorn server.main:app --host 0.0.0.0 --port 8500 --reload
```
Open your browser at **[http://localhost:8500](http://localhost:8500)** to view the live **Instructor Command Dashboard**.

### 3.3 Start Student Workstation Agent
On student lab computers (or in separate terminal tabs for testing):
```powershell
# Run with custom workstation ID
python -m agent.client_agent --host 127.0.0.1 --port 8500 --client-id LAB-PC-01 --student "Zubair Ahmed"

# Run in mock mode (simulated telemetry for automated tests)
python -m agent.client_agent --host 127.0.0.1 --port 8500 --client-id LAB-PC-02 --mock
```

---

## 4. Automated Test Suite (DoD Verification)

Run the test suite directly with pytest:
```powershell
pytest -v tests/
```

All test cases verify:
- Negative string & IPv4 boundary validation (`test_schemas.py`).
- Heuristic detection of Reels/Shorts while allowing YouTube tutorials (`test_detector.py`).
- Exact time boundary triggers for 20:50, 20:58, 21:00, 21:05 curfew (`test_curfew.py`).
- Missing heartbeat (>15s) tamper alert generation (`test_manager.py`).
- End-to-end REST and dashboard responses (`test_integration.py`).
