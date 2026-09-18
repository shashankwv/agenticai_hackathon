import json
import os
import socket
import subprocess
import time
from pathlib import Path
import requests

import duckdb
import pandas as pd
import psycopg2
import streamlit as st

# Import State and Agents
from agents.agent_01_requirements.step_04_agent import run_requirements_agent
from agents.agent_02_ui_code_generation.agent_02_ui_code_generation import (
    run_ui_code_generation_agent,
)
from agents.agent_03_etl.agent_03_etl import run_etl_agent
from agents.agent_04_mdm.step_03_agent import run_mdm_agent_autonomous
from agents.agent_04_mdm.step_05_postgres_executor import (
    ensure_postgres_running,
)
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
    Checks if port 8502 is responding. If down, writes st.session_state.project_state.ui_code
    to streamlit_app.py on disk and spawns the background process.
    """
    health_url = "http://127.0.0.1:8502/_stcore/health"

    try:
        resp = requests.get(health_url, timeout=1.5)
        if resp.status_code == 200:
            return True
    except Exception:
        pass

    # Dynamic File Creation from Loaded State
    ui_code_content = getattr(state_obj, "ui_code", None)
    if not UI_FILE_PATH.exists() and ui_code_content and ui_code_content.strip():
        with open(UI_FILE_PATH, "w", encoding="utf-8") as f:
            f.write(ui_code_content)

    if not UI_FILE_PATH.exists():
        return False

    for attempt in range(1, max_retries + 1):
        try:
            subprocess.Popen(
                [
                    "streamlit",
                    "run",
                    "streamlit_app.py",
                    "--server.port",
                    "8502",
                    "--server.headless",
                    "true",
                ],
                cwd=PROJECT_ROOT,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            for _ in range(10):
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


# --- STREAMLIT CONFIGURATION & ACCESSIBLE UI DESIGN SYSTEM ---
st.set_page_config(
    page_title="Autonomous SDLC & MDM Platform", page_icon="⚡", layout="wide"
)

st.markdown(
    """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    /* 1. Eliminate White Space Top Header Bug */
    header[data-testid="stHeader"] {
        background-color: transparent !important;
        height: 0rem !important;
    }

    /* 2. Base Theme & High Contrast Setup */
    html, body, .stApp {
        background-color: #0F172A !important;
        color: #F8FAFC !important;
        font-family: 'Inter', -apple-system, sans-serif !important;
    }

    .block-container {
        padding-top: 1rem !important;
        padding-bottom: 2rem !important;
        max-width: 98% !important;
    }

    /* 3. High-Contrast Guardrails for Labels & Titles */
    label, [data-testid="stWidgetLabel"] p, label p {
        color: #CBD5E1 !important;
        font-weight: 600 !important;
        font-size: 0.68rem !important;
        margin-bottom: 0.1rem !important;
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

    /* 4. Complete Input Container Dark Overrides (Fixes White Padding Bug) */
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

    div[data-baseweb="input"] input,
    div[data-baseweb="base-input"] input,
    input[type="text"] {
        background-color: #1E293B !important;
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 0.72rem !important;
        padding: 0.25rem 0.5rem !important;
        height: 28px !important;
        line-height: 28px !important;
        border: none !important;
    }

    /* Focused State Rules */
    div[data-baseweb="input"]:focus-within,
    [data-testid="stTextInput"] > div:focus-within {
        border-color: #38BDF8 !important;
        box-shadow: 0 0 0 1px #38BDF8 !important;
    }

    input::placeholder {
        color: #94A3B8 !important;
        -webkit-text-fill-color: #94A3B8 !important;
    }

    /* 5. Button High-Contrast & Scaled Compact Setup */
    div.stButton > button, 
    div.stDownloadButton > button, 
    div.stLinkButton > a,
    div[data-testid="stFormSubmitButton"] > button {
        background-color: #1E293B !important;
        color: #F8FAFC !important;
        border: 1px solid #38BDF8 !important;
        border-radius: 5px !important;
        font-weight: 500 !important;
        font-size: 0.68rem !important;
        padding: 0.1rem 0.4rem !important;
        min-height: 28px !important;
        height: 28px !important;
        line-height: 1.0 !important;
        transition: all 0.2s ease-in-out !important;
        white-space: nowrap !important;
        text-overflow: ellipsis !important;
        overflow: hidden !important;
    }

    div.stButton > button:hover, 
    div.stDownloadButton > button:hover, 
    div.stLinkButton > a:hover,
    div[data-testid="stFormSubmitButton"] > button:hover {
        background-color: #38BDF8 !important;
        color: #0F172A !important;
        border-color: #38BDF8 !important;
        box-shadow: 0 2px 8px rgba(56, 189, 248, 0.25) !important;
    }

    div.stButton > button[kind="primary"] {
        background-color: #0284C7 !important;
        color: #FFFFFF !important;
        border: 1px solid #38BDF8 !important;
    }

    div.stButton > button[kind="primary"]:hover {
        background-color: #38BDF8 !important;
        color: #0F172A !important;
    }

    /* File Uploader Target Overrides - Explicit Visibility Fix */
    div[data-testid="stFileUploader"] {
        background-color: transparent !important;
        border: none !important;
        padding: 0 !important;
    }

    div[data-testid="stFileUploader"] section {
        padding: 0 !important;
        background-color: transparent !important;
        border: none !important;
    }

    div[data-testid="stFileUploader"] section small,
    div[data-testid="stFileUploader"] section [data-testid="stFileUploaderInstructions"] {
        display: none !important;
    }

    div[data-testid="stFileUploader"] button[data-testid="baseButton-secondary"],
    div[data-testid="stFileUploader"] section button {
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        background-color: #1E293B !important;
        color: #F8FAFC !important;
        border: 1px solid #38BDF8 !important;
        border-radius: 5px !important;
        font-weight: 500 !important;
        font-size: 0.68rem !important;
        height: 28px !important;
        min-height: 28px !important;
        width: 100% !important;
        margin: 0 !important;
        cursor: pointer !important;
    }

    div[data-testid="stFileUploader"] section button:hover {
        background-color: #38BDF8 !important;
        color: #0F172A !important;
    }

    /* 6. Modern Compact Hero Bar (Wrapped strictly around content) */
    .hero-container {
        background: #1E293B;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 0.8rem 1.25rem;
        margin-bottom: 0.8rem;
        display: inline-flex;
        flex-direction: column;
        width: auto;
        max-width: fit-content;
    }
    
    .hero-title {
        font-size: 1.3rem;
        font-weight: 700;
        color: #38BDF8;
        letter-spacing: -0.01em;
        margin: 0;
        display: flex;
        align-items: center;
        gap: 0.4rem;
    }

    .hero-info-icon {
        font-size: 0.85rem;
        color: #94A3B8;
        cursor: help;
        transition: color 0.2s ease;
    }

    .hero-info-icon:hover {
        color: #38BDF8;
    }

    .hero-subtitle {
        font-size: 0.78rem;
        color: #94A3B8;
        margin-top: 0.1rem;
    }

    /* 7. Narrowed Sidebar (200px) & Tight Padding */
    section[data-testid="stSidebar"] {
        background-color: #1E293B !important;
        border-right: 1px solid #334155 !important;
        width: 200px !important;
        min-width: 200px !important;
    }
    
    section[data-testid="stSidebar"] .block-container {
        padding-top: 0.6rem !important;
        padding-left: 0.35rem !important;
        padding-right: 0.35rem !important;
    }

    /* Custom column gap compression inside sidebar */
    section[data-testid="stSidebar"] [data-testid="column"] {
        padding-left: 0.15rem !important;
        padding-right: 0.15rem !important;
    }

    section[data-testid="stSidebar"] h1, 
    section[data-testid="stSidebar"] h2, 
    section[data-testid="stSidebar"] h3, 
    section[data-testid="stSidebar"] h4 {
        color: #F8FAFC !important;
        font-size: 0.72rem !important;
        font-weight: 700 !important;
        margin-top: 0.15rem !important;
        margin-bottom: 0.15rem !important;
    }

    .sidebar-section-header {
        font-size: 0.72rem;
        font-weight: 700;
        color: #F8FAFC;
        display: flex;
        align-items: center;
        gap: 0.2rem;
        margin-bottom: 0.25rem;
    }

    /* Toggle text size adjustment */
    section[data-testid="stSidebar"] [data-testid="stCheckbox"] label p {
        font-size: 0.68rem !important;
    }

    /* 8. Pipeline Step Card Styling */
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

    /* 9. Terminal Console Logging Area */
    .terminal-card {
        background-color: #020617;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 0.75rem;
        font-family: 'JetBrains Mono', monospace;
        font-size: 0.75rem;
        color: #38BDF8;
        height: 185px;
        overflow-y: auto;
    }
    
    .terminal-log-line {
        margin-bottom: 0.25rem;
        line-height: 1.3;
        min-height: 1.1em;
    }

    .terminal-time {
        color: #64748B;
        margin-right: 0.4rem;
    }

    /* 10. Tab Bar Formatting & Wrap Fix */
    div[data-testid="stTabs"] [data-baseweb="tab-list"] {
        flex-wrap: wrap !important;
        gap: 0.25rem;
        background-color: transparent !important;
    }

    button[data-baseweb="tab"] {
        background-color: #1E293B !important;
        border-radius: 5px !important;
        padding: 0.35rem 0.75rem !important;
        color: #94A3B8 !important;
        font-size: 0.78rem !important;
        border: 1px solid #334155 !important;
    }

    button[aria-selected="true"] {
        background-color: #0F172A !important;
        color: #38BDF8 !important;
        border-color: #38BDF8 !important;
        font-weight: 600 !important;
    }

    /* 11. Compact Metric Badges Fix */
    div[data-testid="stMetric"] {
        background-color: #1E293B;
        border: 1px solid #334155;
        border-radius: 8px;
        padding: 0.4rem 0.6rem;
    }
    
    div[data-testid="stMetricLabel"] p {
        color: #94A3B8 !important;
        font-size: 0.68rem !important;
        font-weight: 600 !important;
        text-transform: uppercase;
    }

    div[data-testid="stMetricValue"] div {
        color: #F8FAFC !important;
        font-size: 0.85rem !important;
        font-weight: 700 !important;
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

state = st.session_state.project_state


def add_log(message: str, level: str = "INFO"):
    """Adds a timestamped log entry to the in-memory log list."""
    timestamp = time.strftime("%H:%M:%S") if message else ""
    st.session_state.execution_logs.append(
        {"time": timestamp, "message": message, "level": level}
    )


if not st.session_state.execution_logs:
    add_log("Engine initialized. Ready for agent pipeline execution.")


# --- HEADER HERO SECTION ---
st.markdown(
    """
    <div class="hero-container">
        <div class="hero-title">
            ⚡ Enterprise SDLC & MDM Engine 
            <span class="hero-info-icon" title="This platform manages a multi-agent workflow. Outputs from Phase 1 continuously flow into downstream UI code generation, ETL definitions, and target relational database DDL.">ⓘ</span>
        </div>
        <div class="hero-subtitle">Decoupled Multi-Agent Autonomous Orchestration • Self-Healing UI • State Engine</div>
    </div>
    """,
    unsafe_allow_html=True,
)

# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    # 1. Business Requirements and Jira Header & Side-by-Side Links
    st.markdown(
        '<div class="sidebar-section-header">Reqs & Jira <span title="Direct links to your enterprise Atlassian workspace where requirements and tasks are hosted.">ⓘ</span></div>',
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

    st.markdown("<div style='margin: 0.25rem 0; border-bottom: 1px solid #334155;'></div>", unsafe_allow_html=True)

    # 2. Pipeline Parameters Side-by-Side Inputs
    st.markdown('<div class="sidebar-section-header">⚙️ Parameters</div>', unsafe_allow_html=True)
    
    col_p1, col_p2 = st.columns(2)
    with col_p1:
        page_id_input = st.text_input("Page ID", value="1966082", key="sb_page_id")
    with col_p2:
        project_key_input = st.text_input("Project Key", value="CBC3", key="sb_proj_key")

    st.markdown("<div style='margin: 0.25rem 0; border-bottom: 1px solid #334155;'></div>", unsafe_allow_html=True)

    # 3. Action Controls Side-by-Side Buttons
    st.markdown('<div class="sidebar-section-header">🚀 Actions</div>', unsafe_allow_html=True)
    
    col_btn1, col_btn2 = st.columns(2)
    with col_btn1:
        run_pipeline_clicked = st.button("⚡ Run", type="primary", use_container_width=True)
    with col_btn2:
        reset_clicked = st.button("🧹 Reset", use_container_width=True)

    if run_pipeline_clicked:
        pipeline_start_time = time.perf_counter()
        if st.session_state.execution_logs:
            add_log("")
        add_log("Initiating Full Pipeline Execution...", "EXEC")
        
        with st.spinner("Orchestrating agents..."):
            # Agent 01
            add_log("")
            add_log("[1/4] Executing Agent 01 (Requirements Parsing)...")
            t_start = time.perf_counter()
            state = run_requirements_agent(
                state, page_id=page_id_input, project_key=project_key_input
            )
            elapsed_a1 = time.perf_counter() - t_start
            add_log(f"Agent 01 Complete (<b>Took {elapsed_a1:.2f}s</b>).", "SUCCESS")

            # Agent 02
            add_log("")
            add_log("[2/4] Executing Agent 02 (UI Engine Code Generation)...")
            t_start = time.perf_counter()
            state = run_ui_code_generation_agent(state)
            elapsed_a2 = time.perf_counter() - t_start
            ui_alive = ensure_ui_server_running(state, max_retries=3)
            add_log(f"Agent 02 Complete (<b>Took {elapsed_a2:.2f}s</b>).", "SUCCESS")
            if ui_alive:
                add_log("UI Server Online on Port 8502.", "SUCCESS")
            else:
                add_log("Port 8502 offline.", "WARN")

            # Agent 03
            add_log("")
            add_log("[3/4] Executing Agent 03 (ETL Processing & DuckDB)...")
            t_start = time.perf_counter()
            state = run_etl_agent(state)
            elapsed_a3 = time.perf_counter() - t_start
            add_log(f"Agent 03 Complete (<b>Took {elapsed_a3:.2f}s</b>).", "SUCCESS")

            # Agent 04
            add_log("")
            add_log("[4/4] Executing Agent 04 (MDM DDL & Postgres Execution)...")
            t_start = time.perf_counter()
            state = run_mdm_agent_autonomous(state, execute_live=st.session_state.get("sb_exec_live", True))
            elapsed_a4 = time.perf_counter() - t_start
            add_log(f"Agent 04 Complete (<b>Took {elapsed_a4:.2f}s</b>).", "SUCCESS")

        total_elapsed = time.perf_counter() - pipeline_start_time
        add_log("")
        add_log(f"Full Pipeline Execution Complete in <b>Took {total_elapsed:.2f}s</b>!", "SUCCESS")
        st.session_state.project_state = state
        st.toast("🎉 Pipeline Executed Successfully!")
        st.rerun()

    if reset_clicked:
        st.session_state.project_state = ProjectState()
        st.session_state.execution_logs = []
        add_log("System state and memory reset.")
        st.toast("✨ System Reset Complete!")
        st.rerun()

    st.markdown("<div style='margin: 0.15rem 0;'></div>", unsafe_allow_html=True)
    
    # 4. Toggle Button
    execute_live = st.toggle(
        "Execute Live DB",
        value=True,
        key="sb_exec_live",
        help="Toggle OFF to generate DDL scripts without running live database queries."
    )


# --- MAIN CANVAS: EVENLY ALIGNED AGENTS & LOG TERMINAL ---
col_pipeline, col_terminal = st.columns([3, 2])

with col_pipeline:
    st.markdown("<h6 style='margin-bottom: 0.4rem; color: #F8FAFC;'>🎛️ Agent Execution Grid</h6>", unsafe_allow_html=True)
    
    col_a1, col_a2, col_a3, col_a4 = st.columns(4)

    with col_a1:
        st.markdown(
            """
            <div class="pipeline-step-card">
                <span class="step-badge">Phase 1</span>
                <div style="font-size: 0.75rem; font-weight:600; color:#F8FAFC;">Requirements</div>
            </div>
            """, 
            unsafe_allow_html=True
        )
        if st.button("Run Phase 1", key="btn_a1", use_container_width=True):
            if st.session_state.execution_logs:
                add_log("")
            add_log("Agent 01 Triggered: Requirements Parsing...")
            start_time = time.perf_counter()
            with st.spinner("Parsing requirements..."):
                state = run_requirements_agent(
                    state, page_id=page_id_input, project_key=project_key_input
                )
                st.session_state.project_state = state
            elapsed = time.perf_counter() - start_time
            add_log(f"Agent 01 Complete (<b>Took {elapsed:.2f}s</b>).", "SUCCESS")
            st.toast("Phase 1 Complete!")
            st.rerun()

    with col_a2:
        st.markdown(
            """
            <div class="pipeline-step-card">
                <span class="step-badge">Phase 2</span>
                <div style="font-size: 0.75rem; font-weight:600; color:#F8FAFC;">UI Generator</div>
            </div>
            """, 
            unsafe_allow_html=True
        )
        if st.button("Run Phase 2", key="btn_a2", use_container_width=True):
            if st.session_state.execution_logs:
                add_log("")
            add_log("Agent 02 Triggered: UI Generation...")
            start_time = time.perf_counter()
            with st.spinner("Generating UI Code..."):
                state = run_ui_code_generation_agent(state)
                st.session_state.project_state = state
                ui_alive = ensure_ui_server_running(state, max_retries=3)
            elapsed = time.perf_counter() - start_time
            
            add_log(f"Agent 02 Complete (<b>Took {elapsed:.2f}s</b>).", "SUCCESS")
            if ui_alive:
                add_log("UI Server Online on Port 8502.", "SUCCESS")
            else:
                add_log("Port 8502 offline.", "WARN")
            st.toast("Phase 2 Complete!")
            st.rerun()

    with col_a3:
        st.markdown(
            """
            <div class="pipeline-step-card">
                <span class="step-badge">Phase 3</span>
                <div style="font-size: 0.75rem; font-weight:600; color:#F8FAFC;">ETL Engine</div>
            </div>
            """, 
            unsafe_allow_html=True
        )
        if st.button("Run Phase 3", key="btn_a3", use_container_width=True):
            if st.session_state.execution_logs:
                add_log("")
            add_log("Agent 03 Triggered: Staging ETL Generation...")
            start_time = time.perf_counter()
            with st.spinner("Executing Staging ETL..."):
                state = run_etl_agent(state)
                st.session_state.project_state = state
            elapsed = time.perf_counter() - start_time
            add_log(f"Agent 03 Complete (<b>Took {elapsed:.2f}s</b>). Staging Data Ready.", "SUCCESS")
            st.toast("Phase 3 Complete!")
            st.rerun()

    with col_a4:
        st.markdown(
            """
            <div class="pipeline-step-card">
                <span class="step-badge">Phase 4</span>
                <div style="font-size: 0.75rem; font-weight:600; color:#F8FAFC;">MDM & DB</div>
            </div>
            """, 
            unsafe_allow_html=True
        )
        if st.button("Run Phase 4", key="btn_a4", use_container_width=True):
            if st.session_state.execution_logs:
                add_log("")
            add_log("Agent 04 Triggered: DDL Creation & DB Deployment...")
            start_time = time.perf_counter()
            with st.spinner("Deploying MDM Schema..."):
                state = run_mdm_agent_autonomous(state, execute_live=execute_live)
                st.session_state.project_state = state
            elapsed = time.perf_counter() - start_time
            add_log(f"Agent 04 Complete (<b>Took {elapsed:.2f}s</b>). DB Updated.", "SUCCESS")
            st.toast("Phase 4 Complete!")
            st.rerun()

with col_terminal:
    st.markdown("<h6 style='margin-bottom: 0.4rem; color: #F8FAFC;'>💻 Console Log Output</h6>", unsafe_allow_html=True)
    
    # Chronological rendering (ascending order) with auto-scrolling
    terminal_html = '<div id="terminal-box" class="terminal-card">'
    for log in st.session_state.execution_logs:
        if not log["message"]:
            terminal_html += '<div class="terminal-log-line">&nbsp;</div>'
            continue

        color = "#38BDF8"
        if log["level"] == "SUCCESS":
            color = "#34D399"
        elif log["level"] == "WARN":
            color = "#FBBF24"
        elif log["level"] == "EXEC":
            color = "#A78BFA"

        time_prefix = f'<span class="terminal-time">[{log["time"]}]</span> ' if log["time"] else ''
        terminal_html += f'<div class="terminal-log-line">{time_prefix}<span style="color: {color};">{log["message"]}</span></div>'
    terminal_html += "</div>"
    terminal_html += """
    <script>
        var tBox = document.getElementById("terminal-box");
        if (tBox) { tBox.scrollTop = tBox.scrollHeight; }
    </script>
    """
    st.markdown(terminal_html, unsafe_allow_html=True)

st.markdown("<div style='margin: 1rem 0; border-bottom: 1px solid #334155;'></div>", unsafe_allow_html=True)


# --- TAB NAVIGATION & RESULTS ---
tab_overview, tab_a1, tab_a2, tab_a3, tab_a4 = st.tabs(
    [
        "🚀 Overview",
        "📋 Phase 1: Requirements",
        "🖥️ Phase 2: UI Code",
        "⚙️ Phase 3: ETL & DuckDB",
        "🗄️ Phase 4: MDM & Postgres",
    ]
)

# Tab 1: Executive Overview
with tab_overview:
    st.markdown("<h6 style='color: #F8FAFC; margin-bottom: 0.75rem;'>System Readiness Status</h6>", unsafe_allow_html=True)
    
    m1, m2, m3, m4 = st.columns(4)

    a1_done = hasattr(state, "jira_parsed_data") and bool(state.jira_parsed_data)
    a2_done = hasattr(state, "ui_code") and bool(state.ui_code)
    a3_done = hasattr(state, "etl_code") and bool(state.etl_code)
    a4_done = hasattr(state, "mdm_ddl") and bool(state.mdm_ddl)

    m1.metric("Requirements (A1)", "READY ✅" if a1_done else "PENDING ⚪")
    m2.metric("UI Engine (A2)", "READY ✅" if a2_done else "PENDING ⚪")
    m3.metric("ETL Staging (A3)", "READY ✅" if a3_done else "PENDING ⚪")
    m4.metric("MDM Deploy (A4)", "READY ✅" if a4_done else "PENDING ⚪")

# Tab 2: Requirements
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

# Tab 3: Generated UI Code
with tab_a2:
    st.markdown("<h6 style='color: #F8FAFC;'>Generated Streamlit UI Application</h6>", unsafe_allow_html=True)
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
        if st.button("🚀 Launch UI Server (Port 8502)", key="btn_launch_ui_direct", use_container_width=True):
            with st.spinner("Connecting to Server..."):
                if ensure_ui_server_running(state, max_retries=3):
                    add_log("UI Server Online.", "SUCCESS")
                    st.success("Server Online!")
                else:
                    st.error("Missing valid `ui_code` in state.")

    with col_u2:
        is_live = ensure_ui_server_running(state, max_retries=1)
        if is_live:
            st.link_button("🌐 Open Active Application", app_url, use_container_width=True)
        else:
            st.info("ℹ️ App Server is offline. Click 'Launch UI Server' to start.")

    with st.expander("🖥️ View Generated UI Code", expanded=False):
        st.code(ui_code, language="python")

# Tab 4: ETL Engine & DuckDB Console
with tab_a3:
    with st.expander("⚙️ Generated Staging ETL Code", expanded=False):
        etl_code = getattr(
            state, "etl_code", "# Agent 03 output will appear here after execution."
        )
        st.code(etl_code, language="python")

    st.markdown("<div style='margin: 0.5rem 0;'></div>", unsafe_allow_html=True)

    with st.expander("📊 DuckDB Staging Data Explorer", expanded=False):
        duckdb_file = PROJECT_ROOT / "staging.duckdb"

        if duckdb_file.exists():
            try:
                duck_conn = duckdb.connect(str(duckdb_file), read_only=True)
                tables = duck_conn.execute("SHOW TABLES").fetchdf()

                if not tables.empty and "cleansed_staging_data" in tables["name"].values:
                    duck_df = duck_conn.execute(
                        "SELECT * FROM cleansed_staging_data ORDER BY 1 DESC"
                    ).fetchdf()
                    
                    st.dataframe(duck_df, use_container_width=True)

                    with st.expander("🔍 SQL Console", expanded=False):
                        custom_query = st.text_area(
                            "SQL Query",
                            value="SELECT count(*) as total_records FROM cleansed_staging_data",
                            height=60,
                        )
                        if st.button("Execute Query", key="btn_run_duck_sql"):
                            try:
                                res_df = duck_conn.execute(custom_query).fetchdf()
                                st.dataframe(res_df, use_container_width=True)
                            except Exception as q_err:
                                st.error(f"SQL Error: {q_err}")
                else:
                    st.info("Table `cleansed_staging_data` is not populated yet.")
                duck_conn.close()
            except Exception as duck_err:
                st.error(f"DuckDB Error: {duck_err}")
        else:
            st.warning("⚠️ No `staging.duckdb` database found. Run Phase 3.")

# Tab 5: MDM Target DB & PostgreSQL
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
st.markdown("<div style='margin: 1.5rem 0 1rem 0; border-bottom: 1px solid #334155;'></div>", unsafe_allow_html=True)

with st.expander("🛠️ DevTools: Memory Inspector & File Checkpoints", expanded=False):
    col_import, col_export = st.columns(2)

    with col_import:
        st.markdown("<div style='font-size:0.72rem; font-weight:600; color: #F8FAFC; margin-bottom:0.2rem;'>📥 Import Checkpoint</div>", unsafe_allow_html=True)
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
                    with open(UI_FILE_PATH, "w", encoding="utf-8") as f:
                        f.write(st.session_state.project_state.ui_code)
                
                st.success("State synchronized!")
                st.rerun()
            except Exception as imp_err:
                st.error(f"Failed to import state file: {imp_err}")

    with col_export:
        st.markdown("<div style='font-size:0.72rem; font-weight:600; color: #F8FAFC; margin-bottom:0.2rem;'>📤 Export Checkpoint</div>", unsafe_allow_html=True)
        current_state_json = state.model_dump_json(indent=2)
        st.download_button(
            label="💾 Download JSON",
            data=current_state_json,
            file_name="state_checkpoint.json",
            mime="application/json",
            use_container_width=True,
        )

    st.markdown("<div style='margin: 0.5rem 0; border-bottom: 1px solid #334155;'></div>", unsafe_allow_html=True)

    with st.form("edit_state_form"):
        st.markdown("<div style='font-size:0.72rem; font-weight:600; color: #F8FAFC; margin-bottom:0.2rem;'>⚙️ Edit In-Memory State Payload</div>", unsafe_allow_html=True)
        raw_json_input = st.text_area(
            "JSON Payload",
            value=state.model_dump_json(indent=2),
            height=140,
            label_visibility="collapsed",
        )
        
        col_submit, _ = st.columns([1, 3])
        with col_submit:
            submit_clicked = st.form_submit_button("💾 Save Modifications", use_container_width=True)
            if submit_clicked:
                try:
                    updated_dict = json.loads(raw_json_input)
                    st.session_state.project_state = ProjectState(**updated_dict)
                    add_log("Modified ProjectState payload in memory.")
                    st.success("Memory updated!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Invalid JSON structure: {e}")