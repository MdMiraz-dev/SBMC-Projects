# SBMC Projects — AI Technical Operations

Welcome to **SBMC Projects**, the central workspace for AI Technical Operations, autonomous agent workflows, and full-stack software development under the SBMC curriculum.

---

## 🛠️ Tech Stack & Runtime Environment

This project strictly adheres to the operational contract defined in [AGENTS.md](AGENTS.md).

- **Python**: CPython `3.12+` with isolated virtual environment (`.venv`)
- **Package & Dependency Management**: `pip`, `uv` / `poetry`
- **Node.js**: Active LTS `24.x` / `20.x`
- **Version Control**: Git
- **Linting & Quality**: `ruff`, `mypy`, ESLint, Prettier

---

## 🚀 Getting Started

### 1. Repository Setup & Virtual Environment

Clone the repository and set up the isolated Python virtual environment:

```powershell
# Initialize and activate Python virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

For POSIX shells (Linux/macOS):
```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Verify Runtime & Tooling

Confirm that runtime environments are correctly installed:

```powershell
python --version   # Target >= 3.12
node --version     # Target >= 20.x LTS
git --version
```

---

## 📋 Architectural Standards & Behavioral Rules

All development within this repository is governed by [AGENTS.md](AGENTS.md):

1. **Stack & Runtime**: Standardized CPython $\ge$ 3.11, LTS Node.js, and modern typed web frameworks.
2. **Architecture Boundary**: Clean Separation of Concerns (SoC) across Presentation, Service, Domain, and Infrastructure layers. Modular subagents instead of single-agent monoliths.
3. **Forbidden Actions**:
   - Zero hardcoded credentials or API keys (enforce `.env`).
   - No destructive filesystem or database commands.
   - No unverified third-party dependencies.
4. **Working Modes**:
   - **Conductor Mode**: Observational discovery, root-cause diagnosis, and planning.
   - **Orchestrator Mode**: Scoped implementation within minimal blast radiuses.
5. **Verification Discipline**: 80% problem awareness upfront, comprehensive negative testing, and schema validation.
6. **Definition of Done (DoD)**: All tests pass, clean git diff, and explicit human review checkpoints.

---

## 🔒 Security & Environment Variables

Never commit sensitive environment variables or secrets to source control.
Use sanitized `.env.example` templates for configuration:

```bash
# Example .env configuration
APP_ENV=development
LOG_LEVEL=info
```
