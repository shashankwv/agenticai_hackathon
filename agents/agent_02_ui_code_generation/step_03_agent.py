import os
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

from core.state import ProjectState
from agents.agent_02_ui_code_generation.step_01_jira_reader import fetch_jira_issue_details
from agents.agent_02_ui_code_generation.step_02_ui_code_generation import generate_ui_code

# --- ABSOLUTE PATH RESOLUTION ---
PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_UI_DIR = PROJECT_ROOT / "frontend-ui"
FRONTEND_APP_TSX = FRONTEND_UI_DIR / "src" / "App.tsx"

REACT_PORT_START = 5173
REACT_PORT_END = 5199


def stop_vite_server() -> None:
    """Stops any running Vite process immediately."""
    try:
        subprocess.run(
            ["pkill", "-9", "-f", "node.*vite"], 
            stdout=subprocess.DEVNULL, 
            stderr=subprocess.DEVNULL
        )
        time.sleep(1)
    except Exception:
        pass


def get_active_vite_port() -> int | None:
    """Scans local ports to find which port Vite is actively listening on."""
    for port in range(REACT_PORT_START, REACT_PORT_END + 1):
        try:
            url = f"http://127.0.0.1:{port}"
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                with urllib.request.urlopen(url, timeout=0.8) as response:
                    body = response.read(2048).decode("utf-8", errors="ignore")
                    if response.status < 500 and ("@vite/client" in body or "root" in body.lower() or "<div" in body.lower()):
                        return port
        except Exception:
            continue
    return None


def restart_vite_and_get_url() -> str:
    """Stops Vite if running, launches a fresh server, and returns the dynamic URL."""
    # 1. Stop existing Vite server instance safely
    stop_vite_server()

    # 2. Launch Vite directly (avoid shell=True to prevent subshell process group issues)
    subprocess.Popen(
        ["npx", "vite", "--host", "0.0.0.0", "--port", "5173"],
        cwd=str(FRONTEND_UI_DIR),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    # 3. Poll for active port (up to 10 seconds timeout)
    active_port = None
    for _ in range(10):
        time.sleep(1)
        active_port = get_active_vite_port()
        if active_port:
            break

    active_port = active_port or REACT_PORT_START

    # 4. Format URL for GitHub Codespaces or Localhost
    codespace_name = os.getenv("CODESPACE_NAME")
    github_domain = os.getenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN", "app.github.dev")

    if codespace_name:
        try:
            subprocess.run(
                ["gh", "codespace", "ports", "visibility", f"{active_port}:public"], 
                stdout=subprocess.DEVNULL, 
                stderr=subprocess.DEVNULL
            )
        except Exception:
            pass
        return f"https://{codespace_name}-{active_port}.{github_domain}/"

    return f"http://localhost:{active_port}/"


def run_ui_code_generation_agent(state: ProjectState) -> ProjectState:
    """Agent 02 (UI): Reads live UI task from Jira, generates clean React TSX code, writes App.tsx, and restarts Vite."""
    if not state.jira_ui_issue_key:
        print("No UI Jira issue key found in state. Skipping UI code generation.")
        return state

    print(f"Fetching Jira details for UI Task: {state.jira_ui_issue_key}...")
    ui_details = fetch_jira_issue_details(state.jira_ui_issue_key)
    
    print("Generating UI Code (React/TypeScript)...")
    # 1. Generate pure TSX code via LLM
    ui_code = generate_ui_code(ui_details)
    state.ui_code = ui_code
    
    # 2. Write generated TSX code directly to frontend-ui/src/App.tsx
    try:
        FRONTEND_APP_TSX.parent.mkdir(parents=True, exist_ok=True)
        FRONTEND_APP_TSX.write_text(ui_code, encoding="utf-8")
        print(f"Successfully wrote generated UI code to {FRONTEND_APP_TSX}")
    except Exception as exc:
        print(f"Failed to write App.tsx: {exc}")

    # 3. Stop existing server, start a fresh server instance, and grab the dynamic URL
    sandbox_url = restart_vite_and_get_url()
    state.ui_sandbox_url = sandbox_url
    print(f"Vite Server restarted and active at: {sandbox_url}")

    return state