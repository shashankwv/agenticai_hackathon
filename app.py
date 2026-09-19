import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
import requests
import signal

import duckdb
import pandas as pd
import psycopg2
import streamlit as st
import streamlit.components.v1 as components

# ============================================================================
# CONSOLIDATED AGENT IMPORTS
# ============================================================================
from agents.agent_01_requirements import run_requirements_agent
from agents.agent_02_ui_code_generation import run_ui_code_generation_agent
from agents.agent_03_etl import run_etl_agent
from agents.agent_04_mdm import run_mdm_agent_autonomous, ensure_postgres_running

from core.state import ProjectState

# --- ABSOLUTE PATH RESOLUTION ---
PROJECT_ROOT = Path(__file__).resolve().parent
UI_FILE_PATH = PROJECT_ROOT / "streamlit_app.py"


# --- HELPER FUNCTIONS FOR SELF-HEALING UI SERVER ENGINE ---
def is_port_open(host: str = "127.0.0.1", port: int = 8502) -> bool:
    """Checks if a TCP port is open and accepting connections."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex((host, port)) == 0


def ensure_ui_server_running(state_obj: ProjectState, max_retries: int = 3) -> bool:
    """
    Kills any process currently running on port 8502, writes fresh ui_code to disk,
    and spawns a clean background Streamlit UI server.
    """
    ui_code_content = getattr(state_obj, "ui_code", None)
    if not ui_code_content or not ui_code_content.strip():
        return False

    # 1. Kill any existing process running on port 8502 to clear stale/frozen servers
    try:
        if os.name == "nt":  # Windows
            subprocess.run(
                ["cmd", "/c", "for /f \"tokens=5\" %a in ('netstat -aon ^| findstr :8502') do taskkill /F /PID %a"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:  # Linux / macOS
            subprocess.run(
                ["fuser", "-k", "8502/tcp"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            subprocess.run(
                ["pkill", "-f", "streamlit_app.py"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        time.sleep(1)  # Allow socket to free up
    except Exception as kill_err:
        print(f"[UI Server Cleanup Warning]: {kill_err}")

    ensure_api_bridge_running()

    # 2. Force rewrite of the file with latest code from memory
    UI_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(UI_FILE_PATH, "w", encoding="utf-8") as f:
        f.write(ui_code_content)

    health_url = "http://127.0.0.1:8502/_stcore/health"

    # 3. Spawn a clean background server instance
    for attempt in range(1, max_retries + 1):
        try:
            subprocess.Popen(
                [
                    "streamlit",
                    "run",
                    str(UI_FILE_PATH.relative_to(PROJECT_ROOT)),
                    "--server.port",
                    "8502",
                    "--server.headless",
                    "true",
                ],
                cwd=PROJECT_ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            for _ in range(12):
                time.sleep(0.5)
                try:
                    res = requests.get(health_url, timeout=1.0)
                    if res.status_code == 200:
                        return True
                except Exception:
                    continue
        except Exception as launch_err:
            print(f"[Self-Healing Attempt {attempt}] Launch error: {launch_err}")

    return False

def ensure_api_bridge_running() -> bool:
    """Spawns the FastAPI backend bridge on port 8000 if not already active."""
    health_url = "http://127.0.0.1:8000/health"
    
    # Check if port 8000 is already active
    try:
        if requests.get(health_url, timeout=1.0).status_code == 200:
            return True
    except Exception:
        pass

    # Launch background process using uvicorn CLI via sys.executable
    try:
        subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "etl.api_bridge:app", "--host", "127.0.0.1", "--port", "8000"],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        
        # Wait up to 5 seconds for backend activation
        for _ in range(10):
            time.sleep(0.5)
            try:
                if requests.get(health_url, timeout=1.0).status_code == 200:
                    return True
            except Exception:
                continue
    except Exception as err:
        print(f"[API Bridge Launch Error]: {err}")
        
    return False

# --- STREAMLIT CONFIGURATION & ACCESSIBLE UI DESIGN SYSTEM ---
st.set_page_config(
    page_title="Autonomous SDLC & MDM Platform", page_icon="⚡", layout="wide"
)

st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    /* 1. Hide Top Streamlit Header Toolbar */
    header[data-testid="stHeader"] {
        height: 0rem !important;
        background-color: transparent !important;
        z-index: 900 !important;
    }

    /* 2. Base Theme Setup */
    html, body, .stApp {
        background-color: #0F172A !important;
        color: #F8FAFC !important;
        font-family: 'Inter', -apple-system, sans-serif !important;
    }

    /* Top padding so content scrolls underneath fixed header */
    .block-container {
        padding-top: 6.5rem !important; 
        padding-bottom: 2rem !important;
        max-width: 98% !important;
    }

    /* 3. High-Contrast Guardrails for Labels & Titles */
    label, [data-testid="stWidgetLabel"] p, label p {
        color: #CBD5E1 !important;
        font-weight: 600 !important;
        font-size: 0.60rem !important;
        margin-bottom: 0.1rem !important;
        white-space: nowrap !important;
    }

    /* Expander Dark Theme Strict Overrides */
    details[data-testid="stExpander"],
    div[data-testid="stExpander"],
    [data-testid="stExpanderDetails"] {
        background-color: #0F172A !important;
        border: 1px solid #334155 !important;
        border-radius: 8px !important;
    }

    summary[data-testid="stExpanderSummary"],
    [data-testid="stExpander"] summary {
        background-color: #1E293B !important;
        color: #F8FAFC !important;
        border-radius: 8px !important;
    }

    summary[data-testid="stExpanderSummary"] span,
    summary[data-testid="stExpanderSummary"] span p,
    [data-testid="stExpander"] summary div p {
        color: #F8FAFC !important;
        font-weight: 600 !important;
        font-size: 0.8rem !important;
    }

    /* 4. Complete Input Container Dark Overrides & Text Area High Contrast */
    div[data-testid="stTextInput"] div,
    div[data-baseweb="input"],
    div[data-baseweb="input"] div,
    div[data-baseweb="base-input"],
    div[data-baseweb="base-input"] div {
        background-color: #1E293B !important;
        border-color: #334155 !important;
        box-shadow: none !important;
        padding: 0 !important;
    }

    div[data-baseweb="input"],
    [data-testid="stTextInput"] > div {
        border: 1px solid #334155 !important;
        border-radius: 6px !important;
        overflow: hidden !important;
    }

    section[data-testid="stSidebar"] div[data-baseweb="input"] input,
    section[data-testid="stSidebar"] div[data-baseweb="base-input"] input,
    section[data-testid="stSidebar"] input[type="text"] {
        background-color: #1E293B !important;
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 0.60rem !important;
        font-weight: 500 !important;
        padding: 0.15rem 0.25rem !important;
        height: 24px !important;
        line-height: 24px !important;
        border: none !important;
    }

    /* High-Contrast Payload & Textarea Overrides */
    div[data-testid="stTextArea"] textarea {
        background-color: #0F172A !important;
        color: #F8FAFC !important;
        -webkit-text-fill-color: #F8FAFC !important;
        font-family: 'JetBrains Mono', monospace !important;
        font-size: 0.75rem !important;
        border: 1px solid #334155 !important;
        border-radius: 6px !important;
        padding: 0.5rem !important;
    }

    div[data-testid="stTextArea"] textarea:focus {
        border-color: #38BDF8 !important;
        box-shadow: 0 0 0 1px #38BDF8 !important;
    }

    div[data-baseweb="input"]:focus-within,
    [data-testid="stTextInput"] > div:focus-within {
        border-color: #38BDF8 !important;
        box-shadow: 0 0 0 1px #38BDF8 !important;
    }

    input::placeholder, textarea::placeholder {
        color: #94A3B8 !important;
        -webkit-text-fill-color: #94A3B8 !important;
    }

    /* 5. SIDEBAR BUTTON & LINK OVERRIDES */
    section[data-testid="stSidebar"] div.stButton > button, 
    section[data-testid="stSidebar"] div.stDownloadButton > button, 
    section[data-testid="stSidebar"] div.stLinkButton > a,
    section[data-testid="stSidebar"] div[data-testid="stFormSubmitButton"] > button {
        background-color: #1E293B !important;
        color: #F8FAFC !important;
        border: 1px solid #38BDF8 !important;
        border-radius: 5px !important;
        font-weight: 600 !important;
        font-size: 0.55rem !important;
        padding: 0.1rem 0.2rem !important;
        min-height: 26px !important;
        height: 26px !important;
        line-height: 1.0 !important;
        transition: all 0.2s ease-in-out !important;
        white-space: nowrap !important;
        text-overflow: ellipsis !important;
        overflow: hidden !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }

    section[data-testid="stSidebar"] div.stLinkButton > a p,
    section[data-testid="stSidebar"] div.stButton > button p {
        font-size: 0.55rem !important;
        font-weight: 600 !important;
        color: #F8FAFC !important;
        margin: 0 !important;
    }

    section[data-testid="stSidebar"] div.stButton > button[kind="primary"] {
        background-color: #0284C7 !important;
        color: #FFFFFF !important;
        border: 1px solid #38BDF8 !important;
    }

    section[data-testid="stSidebar"] div.stButton > button[kind="primary"] p {
        color: #FFFFFF !important;
    }

    section[data-testid="stSidebar"] div.stButton > button:hover, 
    section[data-testid="stSidebar"] div.stDownloadButton > button:hover, 
    section[data-testid="stSidebar"] div.stLinkButton > a:hover,
    section[data-testid="stSidebar"] div[data-testid="stFormSubmitButton"] > button:hover {
        background-color: #38BDF8 !important;
        color: #0F172A !important;
        border-color: #38BDF8 !important;
        box-shadow: 0 2px 8px rgba(56, 189, 248, 0.25) !important;
    }

    section[data-testid="stSidebar"] div.stButton > button:hover p,
    section[data-testid="stSidebar"] div.stLinkButton > a:hover p {
        color: #0F172A !important;
    }

    /* 6. MAIN CANVAS BUTTONS & CHECKPOINT ALIGNMENT OVERRIDES */
    div[data-testid="stMainBlockContainer"] div.stButton > button,
    div[data-testid="stMainBlockContainer"] div.stDownloadButton > button {
        background-color: #1E293B !important;
        color: #F8FAFC !important;
        border: 1px solid #38BDF8 !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        font-size: 0.72rem !important;
        padding: 0.35rem 0.5rem !important;
        height: 38px !important;
        min-height: 38px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
        transition: all 0.2s ease-in-out !important;
    }

    div[data-testid="stMainBlockContainer"] div.stButton > button p,
    div[data-testid="stMainBlockContainer"] div.stDownloadButton > button p {
        color: #F8FAFC !important;
        font-weight: 600 !important;
        font-size: 0.72rem !important;
        margin: 0 !important;
    }

    div[data-testid="stMainBlockContainer"] div.stButton > button:hover,
    div[data-testid="stMainBlockContainer"] div.stDownloadButton > button:hover {
        background-color: #38BDF8 !important;
        color: #0F172A !important;
        border-color: #38BDF8 !important;
        box-shadow: 0 0 10px rgba(56, 189, 248, 0.4) !important;
    }

    div[data-testid="stMainBlockContainer"] div.stButton > button:hover p,
    div[data-testid="stMainBlockContainer"] div.stDownloadButton > button:hover p {
        color: #0F172A !important;
    }

    /* Form Submit / Save Modifications Styling */
    div[data-testid="stFormSubmitButton"] > button {
        background-color: #0284C7 !important;
        color: #FFFFFF !important;
        border: 1px solid #38BDF8 !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        font-size: 0.72rem !important;
        height: 38px !important;
        min-height: 38px !important;
    }

    div[data-testid="stFormSubmitButton"] > button p {
        color: #FFFFFF !important;
        font-weight: 600 !important;
        margin: 0 !important;
    }

    div[data-testid="stFormSubmitButton"] > button:hover {
        background-color: #38BDF8 !important;
        color: #0F172A !important;
        box-shadow: 0 0 10px rgba(56, 189, 248, 0.4) !important;
    }

    div[data-testid="stFormSubmitButton"] > button:hover p {
        color: #0F172A !important;
    }

    /* File Uploader Dimension & High-Contrast Matching */
    div[data-testid="stFileUploader"] {
        width: 100% !important;
    }

    div[data-testid="stFileUploader"] section {
        background-color: #1E293B !important;
        border: 1px solid #38BDF8 !important;
        border-radius: 6px !important;
        padding: 0.2rem 0.5rem !important;
        height: 38px !important;
        min-height: 38px !important;
        display: flex !important;
        align-items: center !important;
        justify-content: center !important;
    }

    div[data-testid="stFileUploader"] section *,
    div[data-testid="stFileUploader"] section span,
    div[data-testid="stFileUploader"] section small,
    div[data-testid="stFileUploader"] section button {
        color: #F8FAFC !important;
        -webkit-text-fill-color: #F8FAFC !important;
        font-size: 0.68rem !important;
    }

    /* 7. Precision Frozen Header Panel & Mask */
    .hero-fixed-wrapper {
        position: fixed;
        top: 0;
        left: 200px;
        right: 0;
        height: 5.2rem;
        z-index: 99999;
        background-color: #0F172A;
        padding: 0.8rem 2rem 0.5rem 2rem;
        border-bottom: 1px solid #1E293B;
    }

    .hero-container {
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 6px;
        padding: 0.35rem 0.75rem;
        display: inline-flex;
        flex-direction: column;
        width: auto;
        max-width: fit-content;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
    }
    
    .hero-title {
        font-size: 0.82rem;
        font-weight: 600;
        color: #38BDF8;
        letter-spacing: -0.01em;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 0.3rem;
        line-height: 1.2;
    }

    .hero-info-icon {
        font-size: 0.7rem;
        color: #94A3B8;
        cursor: help;
        transition: color 0.2s ease;
    }

    .hero-info-icon:hover {
        color: #38BDF8;
    }

    .hero-subtitle {
        font-size: 0.63rem;
        font-weight: 400;
        color: #94A3B8;
        margin-top: 0.05rem;
        line-height: 1.1;
    }

    div[data-testid="stMarkdownContainer"]:has(.hero-fixed-wrapper) {
        position: fixed;
        top: 0;
        left: 0;
        right: 0;
        z-index: 99999;
    }

    /* 8. Narrowed Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #1E293B !important;
        border-right: 1px solid #334155 !important;
        width: 200px !important;
        min-width: 200px !important;
        z-index: 100000 !important;
    }
    
    section[data-testid="stSidebar"] .block-container {
        padding-top: 0.6rem !important;
        padding-left: 0.35rem !important;
        padding-right: 0.35rem !important;
    }

    .sidebar-section-header {
        font-size: 0.65rem;
        font-weight: 700;
        color: #F8FAFC;
        display: flex;
        align-items: center;
        gap: 0.2rem;
        margin-bottom: 0.25rem;
        white-space: nowrap;
    }

    /* 9. Pipeline Step Card & Status Pill Styling */
    .pipeline-step-card {
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 0.5rem;
        text-align: center;
        height: 60px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        align-items: center;
        margin-bottom: 0.4rem;
    }

    .step-badge {
        font-size: 0.58rem;
        font-weight: 700;
        text-transform: uppercase;
        background: rgba(56, 189, 248, 0.15);
        color: #38BDF8;
        padding: 1px 5px;
        border-radius: 4px;
        margin-bottom: 0.15rem;
    }

    .status-pill {
        display: block;
        text-align: center;
        margin-top: 0.35rem;
        padding: 0.2rem 0.4rem;
        border-radius: 4px;
        font-size: 0.65rem;
        font-weight: 600;
        letter-spacing: 0.02em;
    }

    .status-pill-ready {
        background-color: rgba(52, 211, 153, 0.12);
        color: #34D399;
        border: 1px solid rgba(52, 211, 153, 0.3);
    }

    .status-pill-pending {
        background-color: rgba(148, 163, 184, 0.12);
        color: #94A3B8;
        border: 1px solid rgba(148, 163, 184, 0.25);
    }

    /* 10. STRICT TAB WIDTH & OVERFLOW PREVENTION */
    div[data-baseweb="tab-list"] {
        display: flex !important;
        width: 100% !important;
        gap: 4px !important;
    }

    button[data-baseweb="tab"] {
        flex: 1 1 0px !important;
        min-width: 0 !important;
        padding: 0.25rem 0.3rem !important;
        justify-content: center !important;
        text-align: center !important;
    }

    button[data-baseweb="tab"] p,
    button[data-baseweb="tab"] span {
        font-size: 0.68rem !important;
        font-weight: 600 !important;
        white-space: nowrap !important;
        overflow: hidden !important;
        text-overflow: ellipsis !important;
    }

    /* Hide tab-scroll arrow buttons completely */
    div[data-testid="stTabs"] button[aria-label="Previous tab"],
    div[data-testid="stTabs"] button[aria-label="Next tab"] {
        display: none !important;
    }

    /* Scrollbars */
    ::-webkit-scrollbar {
        width: 4px;
        height: 4px;
    }
    ::-webkit-scrollbar-track {
        background: #0F172A;
    }
    ::-webkit-scrollbar-thumb {
        background: #334155;
        border-radius: 3px;
    }
</style>
""",
    unsafe_allow_html=True,
)

# --- SESSION STATE INITIALIZATION ---
if "project_state" not in st.session_state:
    st.session_state.project_state = ProjectState()

if "execution_logs" not in st.session_state:
    st.session_state.execution_logs = []

if "has_initialized" not in st.session_state:
    st.session_state.has_initialized = False

state = st.session_state.project_state
terminal_placeholder = None


def render_terminal_component():
    """Renders formatted console output inside an isolated HTML component with auto-scroll logic."""
    log_rows_html = ""
    for log in st.session_state.execution_logs:
        if not log["message"]:
            log_rows_html += '<div style="margin-bottom: 0.25rem; line-height: 1.3; min-height: 1.1em;">&nbsp;</div>'
            continue

        color = "#38BDF8"
        if log["level"] == "SUCCESS":
            color = "#34D399"
        elif log["level"] == "WARN":
            color = "#FBBF24"
        elif log["level"] == "EXEC":
            color = "#A78BFA"

        time_prefix = (
            f'<span style="color: #64748B; margin-right: 0.4rem;">[{log["time"]}]</span> '
            if log["time"]
            else ""
        )
        log_rows_html += f'<div style="margin-bottom: 0.25rem; line-height: 1.3;">{time_prefix}<span style="color: {color};">{log["message"]}</span></div>'

    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{
                margin: 0;
                padding: 0;
                background-color: transparent;
                font-family: 'JetBrains Mono', monospace, monospace;
            }}
            #terminal-container {{
                background-color: #020617;
                border: 1px solid #334155;
                border-radius: 8px;
                padding: 0.75rem;
                font-size: 0.75rem;
                height: 185px;
                box-sizing: border-box;
                overflow-y: auto;
                scroll-behavior: smooth;
            }}
            ::-webkit-scrollbar {{
                width: 4px;
            }}
            ::-webkit-scrollbar-track {{
                background: #0F172A;
            }}
            ::-webkit-scrollbar-thumb {{
                background: #334155;
                border-radius: 3px;
            }}
        </style>
    </head>
    <body>
        <div id="terminal-container">
            {log_rows_html}
        </div>
        <script>
            function scrollToBottom() {{
                var el = document.getElementById("terminal-container");
                if (el) {{
                    el.scrollTop = el.scrollHeight;
                }}
            }}
            scrollToBottom();
            setTimeout(scrollToBottom, 50);
            setTimeout(scrollToBottom, 150);
        </script>
    </body>
    </html>
    """
    components.html(html_code, height=195)


def update_terminal_ui():
    """Flushes and re-renders the terminal frame in real-time."""
    if terminal_placeholder is not None:
        with terminal_placeholder.container():
            render_terminal_component()


def add_log(message: str, level: str = "INFO"):
    """Adds a timestamped log entry to memory and triggers live auto-scrolling UI refresh."""
    timestamp = time.strftime("%H:%M:%S") if message else ""
    st.session_state.execution_logs.append(
        {"time": timestamp, "message": message, "level": level}
    )
    update_terminal_ui()


# Ensure Engine initialized log is created once
if not st.session_state.has_initialized:
    add_log("Engine initialized. Ready for agent pipeline execution.")
    st.session_state.has_initialized = True


# --- HEADER HERO SECTION (FROZEN TOP PANE) ---
st.markdown(
    """
    <div class="hero-fixed-wrapper">
        <div class="hero-container">
            <div class="hero-title">
                ⚡ Enterprise SDLC & MDM Engine 
                <span class="hero-info-icon" title="This platform manages a multi-agent workflow. Outputs from Phase 1 continuously flow into downstream UI code generation, ETL definitions, and target relational database DDL.">ⓘ</span>
            </div>
            <div class="hero-subtitle">Decoupled Multi-Agent Autonomous Orchestration • Self-Healing UI • State Engine</div>
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    st.markdown(
        '<div class="sidebar-section-header">Requirements & Jira <span title="Direct links to your enterprise Atlassian workspace where requirements and tasks are hosted.">ⓘ</span></div>',
        unsafe_allow_html=True,
    )
    atlassian_base = os.getenv("ATLASSIAN_URL", "https://shashankwv.atlassian.net")
    jira_url = f"{atlassian_base}/jira"
    confluence_url = f"{atlassian_base}/wiki"

    col_link1, col_link2 = st.columns(2)
    with col_link1:
        st.link_button("Confluence", confluence_url, use_container_width=True)
    with col_link2:
        st.link_button("Jira Board", jira_url, use_container_width=True)

    st.markdown(
        "<div style='margin: 0.25rem 0; border-bottom: 1px solid #334155;'></div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="sidebar-section-header">⚙️ Parameters</div>',
        unsafe_allow_html=True,
    )
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        page_id_input = st.text_input(
            "Confluence Page ID", value="1966082", key="sb_page_id"
        )
    with col_p2:
        project_key_input = st.text_input(
            "Jira Project Key", value="CBC3", key="sb_proj_key"
        )

    st.markdown(
        "<div style='margin: 0.25rem 0; border-bottom: 1px solid #334155;'></div>",
        unsafe_allow_html=True,
    )

    st.markdown(
        '<div class="sidebar-section-header">🚀 Actions</div>',
        unsafe_allow_html=True,
    )

    run_pipeline_clicked = st.button(
        "⚡ Run end-to-end Pipeline", type="primary", use_container_width=True
    )
    reset_clicked = st.button("🧹 Reset State", use_container_width=True)

    st.markdown("<div style='margin: 0.15rem 0;'></div>", unsafe_allow_html=True)
    execute_live = st.toggle(
        "Execute Live DB",
        value=True,
        key="sb_exec_live",
        help="Toggle OFF to generate DDL scripts without running live database queries.",
    )
    start_fresh = st.toggle(
        "🗑️ Start Fresh (Drop & Recreate)",
        value=False,
        key="sb_start_fresh",
        help="When enabled, agents will drop existing tables and start with a clean slate.",
    )


# --- CHECK PHASE READINESS STATES ---
a1_done = hasattr(state, "jira_ui_task") and bool(state.jira_ui_task)
a2_done = hasattr(state, "ui_code") and bool(state.ui_code)
a3_done = hasattr(state, "etl_code") and bool(state.etl_code)
a4_done = hasattr(state, "mdm_ddl") and bool(state.mdm_ddl)


# --- MAIN CANVAS: EVENLY ALIGNED AGENTS & LOG TERMINAL ---
col_pipeline, col_terminal = st.columns([3, 2])

with col_pipeline:
    st.markdown(
        "<h6 style='margin-bottom: 0.4rem; color: #F8FAFC;'>🎛️ Agent Execution Grid</h6>",
        unsafe_allow_html=True,
    )

    col_a1, col_a2, col_a3, col_a4 = st.columns(4)

    with col_a1:
        st.markdown(
            """
            <div class="pipeline-step-card">
                <span class="step-badge">Phase 1</span>
                <div style="font-size: 0.75rem; font-weight:600; color:#F8FAFC;">Requirements</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        run_phase_1 = st.button("Run Phase 1", key="btn_a1", use_container_width=True)
        status_html = (
            '<div class="status-pill status-pill-ready">READY ✅</div>'
            if a1_done
            else '<div class="status-pill status-pill-pending">PENDING ⚪</div>'
        )
        st.markdown(status_html, unsafe_allow_html=True)

    with col_a2:
        st.markdown(
            """
            <div class="pipeline-step-card">
                <span class="step-badge">Phase 2</span>
                <div style="font-size: 0.75rem; font-weight:600; color:#F8FAFC;">UI Generator</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        run_phase_2 = st.button("Run Phase 2", key="btn_a2", use_container_width=True)
        status_html = (
            '<div class="status-pill status-pill-ready">READY ✅</div>'
            if a2_done
            else '<div class="status-pill status-pill-pending">PENDING ⚪</div>'
        )
        st.markdown(status_html, unsafe_allow_html=True)

    with col_a3:
        st.markdown(
            """
            <div class="pipeline-step-card">
                <span class="step-badge">Phase 3</span>
                <div style="font-size: 0.75rem; font-weight:600; color:#F8FAFC;">ETL Engine</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        run_phase_3 = st.button("Run Phase 3", key="btn_a3", use_container_width=True)
        status_html = (
            '<div class="status-pill status-pill-ready">READY ✅</div>'
            if a3_done
            else '<div class="status-pill status-pill-pending">PENDING ⚪</div>'
        )
        st.markdown(status_html, unsafe_allow_html=True)

    with col_a4:
        st.markdown(
            """
            <div class="pipeline-step-card">
                <span class="step-badge">Phase 4</span>
                <div style="font-size: 0.75rem; font-weight:600; color:#F8FAFC;">MDM Engine</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        run_phase_4 = st.button("Run Phase 4", key="btn_a4", use_container_width=True)
        status_html = (
            '<div class="status-pill status-pill-ready">READY ✅</div>'
            if a4_done
            else '<div class="status-pill status-pill-pending">PENDING ⚪</div>'
        )
        st.markdown(status_html, unsafe_allow_html=True)

with col_terminal:
    st.markdown(
        "<h6 style='margin-bottom: 0.4rem; color: #F8FAFC;'>🖥️ Live Execution Logs</h6>",
        unsafe_allow_html=True,
    )
    terminal_placeholder = st.empty()
    update_terminal_ui()


# --- SIDEBAR & AGENT EXECUTION HANDLERS ---
if run_pipeline_clicked:
    pipeline_start_time = time.perf_counter()
    if st.session_state.execution_logs:
        add_log("")
    add_log("Initiating Full Pipeline Execution...", "EXEC")

    # Agent 01
    add_log("")
    add_log("[1/4] Executing Agent 01 (Requirements Parsing)...", "EXEC")
    add_log("[PROCESSING...] Parsing requirements...", "WARN")
    t_start = time.perf_counter()
    state = run_requirements_agent(
        state, page_id=page_id_input, project_key=project_key_input
    )
    elapsed_a1 = time.perf_counter() - t_start
    if (
        st.session_state.execution_logs
        and st.session_state.execution_logs[-1]["level"] == "WARN"
    ):
        st.session_state.execution_logs.pop()
    add_log(f"Agent 01 Complete (<b>Took {elapsed_a1:.2f}s</b>).", "SUCCESS")

    # Agent 02
    add_log("")
    add_log("[2/4] Executing Agent 02 (UI Engine Code Generation)...", "EXEC")
    add_log("[PROCESSING...] Generating UI Code...", "WARN")
    t_start = time.perf_counter()
    state = run_ui_code_generation_agent(state, reset=start_fresh)
    elapsed_a2 = time.perf_counter() - t_start
    ui_alive = ensure_ui_server_running(state, max_retries=3)
    if (
        st.session_state.execution_logs
        and st.session_state.execution_logs[-1]["level"] == "WARN"
    ):
        st.session_state.execution_logs.pop()
    add_log(f"Agent 02 Complete (<b>Took {elapsed_a2:.2f}s</b>).", "SUCCESS")
    if ui_alive:
        add_log("UI Server Online on Port 8502.", "SUCCESS")
    else:
        add_log("Port 8502 offline.", "WARN")

    # Agent 03
    add_log("")
    add_log("[3/4] Executing Agent 03 (ETL Processing & DuckDB)...", "EXEC")
    add_log("[PROCESSING...] Executing Staging ETL...", "WARN")
    t_start = time.perf_counter()
    state = run_etl_agent(state, reset=start_fresh)
    elapsed_a3 = time.perf_counter() - t_start
    if (
        st.session_state.execution_logs
        and st.session_state.execution_logs[-1]["level"] == "WARN"
    ):
        st.session_state.execution_logs.pop()
    add_log(f"Agent 03 Complete (<b>Took {elapsed_a3:.2f}s</b>).", "SUCCESS")

    # Agent 04
    add_log("")
    add_log("[4/4] Executing Agent 04 (MDM DDL & Postgres Execution)...", "EXEC")
    add_log("[PROCESSING...] Deploying MDM Schema...", "WARN")
    t_start = time.perf_counter()
    state = run_mdm_agent_autonomous(
        state, execute_live=st.session_state.get("sb_exec_live", True), reset=start_fresh
    )
    elapsed_a4 = time.perf_counter() - t_start
    if (
        st.session_state.execution_logs
        and st.session_state.execution_logs[-1]["level"] == "WARN"
    ):
        st.session_state.execution_logs.pop()
    add_log(f"Agent 04 Complete (<b>Took {elapsed_a4:.2f}s</b>).", "SUCCESS")

    total_elapsed = time.perf_counter() - pipeline_start_time
    add_log("")
    add_log(
        f"Full Pipeline Execution Complete in <b>Took {total_elapsed:.2f}s</b>!",
        "SUCCESS",
    )
    st.session_state.project_state = state
    st.toast("🎉 Pipeline Executed Successfully!")
    st.rerun()

if reset_clicked:
    st.session_state.project_state = ProjectState()
    st.session_state.execution_logs = []
    st.session_state.has_initialized = True
    add_log("System state and memory reset.")
    st.toast("✨ System Reset Complete!")
    st.rerun()

# --- PHASE TRIGGER BUTTON HANDLERS ---
if run_phase_1:
    if st.session_state.execution_logs:
        add_log("")
    add_log("Agent 01 Triggered: Requirements Parsing...", "EXEC")
    add_log("[PROCESSING...] Parsing requirements...", "WARN")
    start_time = time.perf_counter()
    state = run_requirements_agent(
        state, page_id=page_id_input, project_key=project_key_input
    )
    st.session_state.project_state = state
    elapsed = time.perf_counter() - start_time
    if (
        st.session_state.execution_logs
        and st.session_state.execution_logs[-1]["level"] == "WARN"
    ):
        st.session_state.execution_logs.pop()
    add_log(f"Agent 01 Complete (<b>Took {elapsed:.2f}s</b>).", "SUCCESS")
    st.toast("Phase 1 Complete!")
    st.rerun()

if run_phase_2:
    if st.session_state.execution_logs:
        add_log("")
    add_log("Agent 02 Triggered: UI Generation...", "EXEC")
    add_log("[PROCESSING...] Generating UI Code...", "WARN")
    start_time = time.perf_counter()
    state = run_ui_code_generation_agent(state, reset=start_fresh)
    st.session_state.project_state = state
    ui_alive = ensure_ui_server_running(state, max_retries=3)
    elapsed = time.perf_counter() - start_time
    if (
        st.session_state.execution_logs
        and st.session_state.execution_logs[-1]["level"] == "WARN"
    ):
        st.session_state.execution_logs.pop()
    add_log(f"Agent 02 Complete (<b>Took {elapsed:.2f}s</b>).", "SUCCESS")
    if ui_alive:
        add_log("UI Server Online on Port 8502.", "SUCCESS")
    else:
        add_log("Port 8502 offline.", "WARN")
    st.toast("Phase 2 Complete!")
    st.rerun()

if run_phase_3:
    if st.session_state.execution_logs:
        add_log("")
    add_log("Agent 03 Triggered: Staging ETL Generation...", "EXEC")
    add_log("[PROCESSING...] Executing Staging ETL...", "WARN")
    start_time = time.perf_counter()
    state = run_etl_agent(state, reset=start_fresh)
    st.session_state.project_state = state
    elapsed = time.perf_counter() - start_time
    if (
        st.session_state.execution_logs
        and st.session_state.execution_logs[-1]["level"] == "WARN"
    ):
        st.session_state.execution_logs.pop()
    add_log(
        f"Agent 03 Complete (<b>Took {elapsed:.2f}s</b>). Staging Data Ready.",
        "SUCCESS",
    )
    st.toast("Phase 3 Complete!")
    st.rerun()

if run_phase_4:
    if st.session_state.execution_logs:
        add_log("")
    add_log("Agent 04 Triggered: DDL Creation & DB Deployment...", "EXEC")
    add_log("[PROCESSING...] Deploying MDM Schema...", "WARN")
    start_time = time.perf_counter()
    state = run_mdm_agent_autonomous(state, execute_live=execute_live, reset=start_fresh)
    st.session_state.project_state = state
    elapsed = time.perf_counter() - start_time
    if (
        st.session_state.execution_logs
        and st.session_state.execution_logs[-1]["level"] == "WARN"
    ):
        st.session_state.execution_logs.pop()
    add_log(f"Agent 04 Complete (<b>Took {elapsed:.2f}s</b>). DB Updated.", "SUCCESS")
    st.toast("Phase 4 Complete!")
    st.rerun()

st.markdown(
    "<div style='margin: 1rem 0; border-bottom: 1px solid #334155;'></div>",
    unsafe_allow_html=True,
)


# --- TAB NAVIGATION & RESULTS ---
tab_a1, tab_a2, tab_a3, tab_a4 = st.tabs(
    [
        "📋 Phase 1: Requirements",
        "🖥️ Phase 2: UI Code",
        "⚙️ Phase 3: ETL",
        "🗄️ Phase 4: MDM & DB",
    ]
)

# Tab 1: Requirements
with tab_a1:
    with st.expander("📋 Parsed Requirements Artifacts", expanded=False):
        st.json(
            {
                "page_id": page_id_input,
                "project_key": project_key_input,
                "jira_ui_key": getattr(state, "jira_ui_issue_key", None),
                "jira_etl_key": getattr(state, "jira_etl_issue_key", None),
                "jira_mdm_key": getattr(state, "jira_mdm_issue_key", None),
                "parsed_requirements": getattr(state, "jira_parsed_data", {}),
            }
        )

# Tab 2: Generated UI Code
with tab_a2:
    st.markdown(
        "<h6 style='color: #F8FAFC;'>Generated Streamlit UI Application</h6>",
        unsafe_allow_html=True,
    )
    ui_code = getattr(
        state, "ui_code", "# Agent 02 output will appear here after execution."
    )

    codespace_name = os.getenv("CODESPACE_NAME")
    port_forward_template = os.getenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN")

    if codespace_name and port_forward_template:
        app_url = f"https://{codespace_name}-8502.{port_forward_template}"
    else:
        app_url = "http://localhost:8502"

    col_u1, col_u2 = st.columns([1, 2])
    with col_u1:
        if st.button(
            "🚀 Launch UI Server (Port 8502)",
            key="btn_launch_ui_direct",
            use_container_width=True,
        ):
            if ensure_ui_server_running(state, max_retries=3):
                add_log("UI Server Online.", "SUCCESS")
                st.success("Server Online!")
            else:
                st.error("Missing valid `ui_code` in state.")

    with col_u2:
        is_live = ensure_ui_server_running(state, max_retries=1)
        if is_live:
            st.link_button(
                "🌐 Open Active Application", app_url, use_container_width=True
            )
        else:
            st.info("ℹ️ App Server is offline. Click 'Launch UI Server' to start.")

    with st.expander("🖥️ View Generated UI Code", expanded=False):
        st.code(ui_code, language="python")


# --- TAB 3: ETL & DUCKDB EXPLORER ---
with tab_a3:
    col_etl_actions1, col_etl_actions2 = st.columns([1, 1])

    with col_etl_actions1:
        if st.button("▶️ Run etl_pipeline.py Execution", use_container_width=True):
            etl_script = PROJECT_ROOT / "etl" / "etl_pipeline.py"
            if etl_script.exists():
                try:
                    # Dynamically run the generated script
                    result = subprocess.run(
                        [sys.executable, str(etl_script)],
                        cwd=PROJECT_ROOT,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )
                    add_log("Executed etl_pipeline.py successfully.", "SUCCESS")
                    st.success("ETL Pipeline executed!")
                    if result.stdout:
                        st.code(result.stdout)
                except Exception as run_err:
                    add_log(f"ETL execution failed: {run_err}", "WARN")
                    st.error(f"ETL Pipeline Execution Failed: {run_err}")
            else:
                st.warning("No `etl_pipeline.py` script found. Run Phase 3 first.")

    with col_etl_actions2:
        if st.button("🔄 Refresh DB View", use_container_width=True):
            st.rerun()

    with st.expander("⚙️ Generated Staging ETL Code", expanded=False):
        etl_code = getattr(
            state, "etl_code", "# Agent 03 output will appear here after execution."
        )
        st.code(etl_code, language="python")

    st.markdown("<div style='margin: 0.5rem 0;'></div>", unsafe_allow_html=True)

    with st.expander("📊 DuckDB Landing & Staging Explorer", expanded=False):
        duckdb_file = PROJECT_ROOT / "etl" / "etl.duckdb"

        # Auto-create table with correct schema including ingested_at on start fresh or initial load
        if not duckdb_file.exists():
            duckdb_file.parent.mkdir(parents=True, exist_ok=True)
            conn_init = duckdb.connect(str(duckdb_file))
            conn_init.execute("""
                CREATE TABLE IF NOT EXISTS landing_ui (
                    id VARCHAR PRIMARY KEY,
                    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    payload JSON
                );
            """)
            conn_init.close()

        try:
            duck_conn = duckdb.connect(str(duckdb_file), read_only=True)
            tables_df = duck_conn.execute("SHOW TABLES").fetchdf()

            if not tables_df.empty:
                available_tables = tables_df["name"].tolist()
                selected_table = st.selectbox("Select Table", available_tables)

                if selected_table:
                    df_view = duck_conn.execute(
                        f'SELECT * FROM "{selected_table}" ORDER BY 1 DESC'
                    ).fetchdf()
                    st.dataframe(df_view, use_container_width=True)

                with st.expander("🔍 SQL Query Runner", expanded=False):
                    custom_query = st.text_area(
                        "SQL Query",
                        value=f'SELECT * FROM "{available_tables[0]}"',
                        height=70,
                    )
                    if st.button("Execute Query", key="btn_run_duck_sql"):
                        try:
                            res_df = duck_conn.execute(custom_query).fetchdf()
                            st.dataframe(res_df, use_container_width=True)
                        except Exception as q_err:
                            st.error(f"SQL Error: {q_err}")
            else:
                st.info("No tables available in `etl.duckdb` yet.")
            duck_conn.close()
        except Exception as duck_err:
            st.error(f"DuckDB Error: {duck_err}")


# Tab 4: MDM Target DB & PostgreSQL
with tab_a4:
    with st.expander("🗄️ Generated PostgreSQL Master Data DDL", expanded=False):
        ddl_code = getattr(
            state,
            "mdm_ddl",
            "-- Agent 04 output will appear here after execution.",
        )
        st.code(ddl_code, language="sql")

    st.markdown("<div style='margin: 0.5rem 0;'></div>", unsafe_allow_html=True)

    with st.expander("📊 PostgreSQL Master Data Table", expanded=False):
        postgres_ready = ensure_postgres_running("mdm-postgres")

        if postgres_ready:
            try:
                conn = psycopg2.connect(
                    "postgresql://postgres:postgres@localhost:5432/mdm_db"
                )
                df = pd.read_sql("SELECT * FROM public.customer_master;", conn)
                conn.close()
                st.dataframe(df, use_container_width=True)
            except Exception as e:
                st.error(f"PostgreSQL Query Error: {e}")
        else:
            st.error("❌ Unable to connect to PostgreSQL container.")


# --- SESSION STATE INSPECTOR & FILE I/O ---
st.markdown(
    "<div style='margin: 1.5rem 0 1rem 0; border-bottom: 1px solid #334155;'></div>",
    unsafe_allow_html=True,
)

with st.expander("🛠️ DevTools: Memory Inspector & File Checkpoints", expanded=False):
    col_import, col_export = st.columns(2)

    with col_import:
        st.markdown(
            "<div style='font-size:0.72rem; font-weight:600; color: #F8FAFC; margin-bottom:0.2rem;'>📥 Import Checkpoint</div>",
            unsafe_allow_html=True,
        )
        uploaded_file = st.file_uploader(
            "Upload JSON state checkpoint file",
            type=["json"],
            key="state_file_uploader",
            label_visibility="collapsed",
        )
        if uploaded_file is not None:
            try:
                file_contents = uploaded_file.read().decode("utf-8")
                data_dict = json.loads(file_contents)
                st.session_state.project_state = ProjectState(**data_dict)
                add_log(f"Imported checkpoint: {uploaded_file.name}")

                if getattr(st.session_state.project_state, "ui_code", None):
                    UI_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
                    with open(UI_FILE_PATH, "w", encoding="utf-8") as f:
                        f.write(st.session_state.project_state.ui_code)

                st.success("State synchronized!")
                st.rerun()
            except Exception as imp_err:
                st.error(f"Failed to import state file: {imp_err}")

    with col_export:
        st.markdown(
            "<div style='font-size:0.72rem; font-weight:600; color: #F8FAFC; margin-bottom:0.2rem;'>📤 Export Checkpoint</div>",
            unsafe_allow_html=True,
        )
        current_state_json = state.model_dump_json(indent=2)
        st.download_button(
            label="💾 Download JSON",
            data=current_state_json,
            file_name="state_checkpoint.json",
            mime="application/json",
            use_container_width=True,
        )

    st.markdown(
        "<div style='margin: 0.5rem 0; border-bottom: 1px solid #334155;'></div>",
        unsafe_allow_html=True,
    )

    with st.form("edit_state_form"):
        st.markdown(
            "<div style='font-size:0.72rem; font-weight:600; color: #F8FAFC; margin-bottom:0.2rem;'>⚙️ Edit In-Memory State Payload</div>",
            unsafe_allow_html=True,
        )
        raw_json_input = st.text_area(
            "JSON Payload",
            value=state.model_dump_json(indent=2),
            height=140,
            label_visibility="collapsed",
        )

        col_submit, _ = st.columns([1, 3])
        with col_submit:
            submit_clicked = st.form_submit_button(
                "💾 Save Modifications", use_container_width=True
            )
            if submit_clicked:
                try:
                    updated_dict = json.loads(raw_json_input)
                    st.session_state.project_state = ProjectState(**updated_dict)
                    add_log("Modified ProjectState payload in memory.")
                    st.success("Memory updated!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Invalid JSON structure: {e}")