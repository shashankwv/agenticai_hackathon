import json
import os
import sys
from pathlib import Path

# Agent 04's self-healing logs use emoji; Windows consoles default to cp1252,
# which raises UnicodeEncodeError on print() and crashes the whole request.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import duckdb
import pandas as pd
import psycopg2
import streamlit as st

# Import State and Agents
from agents.agent_01_requirements.step_04_agent import run_requirements_agent
from agents.agent_02_ui_code_generation.step_03_agent import (
    run_ui_code_generation_agent,
)
from agents.agent_03_etl.agent_03_etl import run_etl_agent
from agents.agent_04_mdm.step_03_agent import run_mdm_agent_autonomous
from agents.agent_04_mdm.step_05_postgres_executor import (
    ensure_postgres_running,
)
from core.state import ProjectState
from core.ui_server import ensure_ui_server_running as _ensure_ui_server_running

# --- ABSOLUTE PATH RESOLUTION ---
PROJECT_ROOT = Path(__file__).resolve().parent
UI_FILE_PATH = PROJECT_ROOT / "streamlit_app.py"


def ensure_ui_server_running(state_obj: ProjectState, max_retries: int = 3) -> bool:
    """Thin wrapper kept for call-site compatibility: delegates to the
    single shared implementation in core/ui_server.py (previously this and
    Agent 02's own orchestrator each had their own separate copy)."""
    return _ensure_ui_server_running(
        ui_code=getattr(state_obj, "ui_code", None), max_retries=max_retries
    )


# --- STREAMLIT CONFIGURATION & STYLING ---
st.set_page_config(
    page_title="Autonomous SDLC Agentic Dashboard", page_icon="🤖", layout="wide"
)

st.markdown(
    """
<style>
    .stApp {
        background-color: #0E1117;
        color: #E0E6ED;
    }
    .main-header {
        font-size: 2.2rem;
        font-weight: 700;
        background: linear-gradient(90deg, #4F46E5, #06B6D4);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 0.2rem;
    }
    .sub-header {
        font-size: 1rem;
        color: #94A3B8;
        margin-bottom: 1.5rem;
    }
    div[data-baseweb="textarea"],
    div[data-baseweb="input"],
    div[data-baseweb="base-input"] {
        background-color: #F1F5F9 !important;
        border-radius: 6px !important;
    }
    textarea, input,
    div[data-baseweb="textarea"] textarea, 
    div[data-baseweb="input"] input {
        color: #0F172A !important;
        -webkit-text-fill-color: #0F172A !important;
        background-color: #F1F5F9 !important;
        font-weight: 600 !important;
        font-family: monospace !important;
    }
    section[data-testid="stSidebar"] input,
    section[data-testid="stSidebar"] textarea {
        color: #0F172A !important;
        -webkit-text-fill-color: #0F172A !important;
        background-color: #F1F5F9 !important;
    }
    div[data-testid="stExpander"] {
        background-color: #1E293B !important;
        border: 1px solid #334155 !important;
        border-radius: 8px !important;
    }
    div[data-testid="stExpander"] details summary span,
    div[data-testid="stExpander"] details summary p {
        color: #FFFFFF !important;
        font-weight: 600 !important;
    }
    div.stButton > button {
        background-color: #1E293B !important;
        color: #FFFFFF !important;
        border: 1px solid #475569 !important;
        font-weight: 700 !important;
    }
    div.stButton > button:hover {
        background-color: #334155 !important;
        color: #38BDF8 !important;
        border-color: #38BDF8 !important;
    }
    div.stButton > button[kind="primary"] {
        background-color: #4F46E5 !important;
        color: #FFFFFF !important;
        border: none !important;
        font-weight: 700 !important;
    }
</style>
""",
    unsafe_allow_html=True,
)

# --- SESSION STATE INITIALIZATION (DEFAULT BLANK STATE) ---
if "project_state" not in st.session_state:
    st.session_state.project_state = ProjectState()

state = st.session_state.project_state

# --- HEADER SECTION ---
st.markdown(
    '<div class="main-header">🤖 Autonomous Agentic SDLC & MDM Engine</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sub-header">Decoupled Multi-Agent Pipeline with In-Memory State Management</div>',
    unsafe_allow_html=True,
)

# --- SIDEBAR CONFIGURATION ---
st.sidebar.header("⚙️ Pipeline Configuration")

atlassian_base = os.getenv("ATLASSIAN_URL", "https://shashankwv.atlassian.net")
jira_url = f"{atlassian_base}/jira"
confluence_url = f"{atlassian_base}/wiki"

col_jira, col_conf = st.sidebar.columns(2)
with col_jira:
    st.link_button("🔗 Open Jira", jira_url, use_container_width=True)
with col_conf:
    st.link_button("📚 Confluence", confluence_url, use_container_width=True)

st.sidebar.divider()

page_id_input = st.sidebar.text_input("Confluence Page ID", value="1966082")
project_key_input = st.sidebar.text_input("Project Key", value="CBC3")

requirement_spec = st.sidebar.text_area(
    "Confluence / Business Specification",
    value=(
        "Generate production master table schema for customer KYC records with"
        " risk scoring."
    ),
)
execute_live = st.sidebar.checkbox(
    "Execute Live on Target DB (PostgreSQL)", value=True
)

st.sidebar.divider()
st.sidebar.subheader("🚀 Execution Control Panel")

if st.sidebar.button("🧹 Reset to Blank State", use_container_width=True):
    st.session_state.project_state = ProjectState()
    st.toast("✨ Session reset to blank state!")
    st.rerun()

if st.sidebar.button(
    "⚡ Run Full Pipeline (End-to-End)", type="primary", use_container_width=True
):
    status_container = st.empty()

    with st.spinner("Executing All Agents..."):
        status_container.info(
            "🔄 [1/4] Executing Agent 01 (Live Confluence Parsing)..."
        )
        state = run_requirements_agent(
            state, page_id=page_id_input, project_key=project_key_input
        )

        status_container.info("🔄 [2/4] Executing Agent 02 (UI Generation)...")
        state = run_ui_code_generation_agent(state)

        status_container.info("🔄 [3/4] Executing Agent 03 (ETL Pipeline)...")
        state = run_etl_agent(state)

        status_container.info(
            "🔄 [4/4] Executing Agent 04 (MDM & Postgres)..."
        )
        state = run_mdm_agent_autonomous(state, execute_live=execute_live)

    status_container.success("🎉 Full Pipeline Executed in Memory!")
    st.session_state.project_state = state
    st.rerun()

# --- AGENT ACTION BUTTONS ROW ---
st.markdown("### 🎛️ Agent Execution Grid")
col_a1, col_a2, col_a3, col_a4 = st.columns(4)

with col_a1:
    st.markdown("**Agent 01: Requirements**")
    if st.button("Run Agent 01", key="btn_a1", use_container_width=True):
        with st.spinner("Parsing Live Confluence & Jira Requirements..."):
            state = run_requirements_agent(
                state, page_id=page_id_input, project_key=project_key_input
            )
            st.session_state.project_state = state
        st.toast("Agent 01 Execution Completed!")
        st.rerun()

with col_a2:
    st.markdown("**Agent 02: UI Generator**")
    if st.button("Run Agent 02", key="btn_a2", use_container_width=True):
        with st.status("🚀 Generating Streamlit UI Code...", expanded=True) as status_box:
            st.write("Fetching Jira task details...")
            st.write("Generating Streamlit Python code...")
            st.write("Saving output to `streamlit_app.py`...")
            
            state = run_ui_code_generation_agent(state)
            st.session_state.project_state = state
            
            st.write("Verifying background process & port 8502...")
            ui_alive = ensure_ui_server_running(state, max_retries=3)
            
            if ui_alive:
                status_box.update(label="✅ Streamlit App Ready on Port 8502!", state="complete")
            else:
                status_box.update(label="⚠️ Code generated, but port 8502 server failed to start.", state="error")
                
        st.toast("Agent 02 Execution Completed!")
        st.rerun()

with col_a3:
    st.markdown("**Agent 03: ETL Engine**")
    if st.button("Run Agent 03", key="btn_a3", use_container_width=True):
        with st.spinner("Generating & Running Staging ETL..."):
            state = run_etl_agent(state)
            st.session_state.project_state = state
        st.toast("Agent 03 Execution Completed!")
        st.rerun()

with col_a4:
    st.markdown("**Agent 04: MDM Target DB**")
    if st.button("Run Agent 04", key="btn_a4", use_container_width=True):
        with st.spinner("Validating DDL & Executing on Postgres..."):
            state = run_mdm_agent_autonomous(state, execute_live=execute_live)
            st.session_state.project_state = state
        st.toast("Agent 04 Execution Completed!")
        st.rerun()

st.divider()

# --- STATE INSPECTOR & FILE DIALOG IMPORT/EXPORT SECTION ---
st.markdown("### 🔍 Live ProjectState Inspector & File IO")

with st.expander("📂 Import / Export / Edit Session State", expanded=False):
    st.markdown("#### 📥 Import State from Computer File")
    uploaded_file = st.file_uploader(
        "Select a `.json` state file from your computer",
        type=["json"],
        key="state_file_uploader",
    )
    if uploaded_file is not None:
        try:
            file_contents = uploaded_file.read().decode("utf-8")
            data_dict = json.loads(file_contents)
            st.session_state.project_state = ProjectState(**data_dict)
            st.success(f"✅ Successfully imported `{uploaded_file.name}` into memory!")
            
            # Automatically write UI code to file upon import if available
            if getattr(st.session_state.project_state, "ui_code", None):
                with open(UI_FILE_PATH, "w", encoding="utf-8") as f:
                    f.write(st.session_state.project_state.ui_code)
                st.info("📄 Synchronized UI code to `streamlit_app.py`.")
            st.rerun()
        except Exception as imp_err:
            st.error(f"Failed to import file: {imp_err}")

    st.divider()
    st.markdown("#### ✏️ Live JSON Memory Inspector")

    with st.form("edit_state_form"):
        raw_json_input = st.text_area(
            "JSON State Payload (Memory)",
            value=state.model_dump_json(indent=2),
            height=250,
        )

        submit_changes = st.form_submit_button("💾 Apply to Session Memory", type="primary")

        if submit_changes:
            try:
                updated_dict = json.loads(raw_json_input)
                st.session_state.project_state = ProjectState(**updated_dict)
                st.success("✅ Memory state updated successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Invalid JSON structure or state payload: {e}")

    st.divider()
    st.markdown("#### 📤 Export State to Computer File")
    
    current_state_json = state.model_dump_json(indent=2)
    st.download_button(
        label="💾 Download Current State as JSON",
        data=current_state_json,
        file_name="state_checkpoint.json",
        mime="application/json",
        use_container_width=True,
    )

st.divider()

# --- MAIN DASHBOARD OUTPUT TABS ---
tab_summary, tab_a1, tab_a2, tab_a3, tab_a4 = st.tabs([
    "📊 Pipeline Status",
    "📋 Agent 01: Requirements Spec",
    "🖥️ Agent 02: Generated UI Code",
    "⚙️ Agent 03: ETL Code",
    "🗄️ Agent 04: MDM & PostgreSQL",
])

# Summary Tab
with tab_summary:
    st.subheader("System Architecture & Execution Overview")
    m1, m2, m3, m4 = st.columns(4)

    a1_done = hasattr(state, "jira_parsed_data") and bool(state.jira_parsed_data)
    a2_done = hasattr(state, "ui_code") and bool(state.ui_code)
    a3_done = hasattr(state, "etl_code") and bool(state.etl_code)
    a4_done = hasattr(state, "mdm_ddl") and bool(state.mdm_ddl)

    m1.metric("Agent 01 (Jira Parser)", "READY ✅" if a1_done else "PENDING ⚪")
    m2.metric("Agent 02 (UI Engine)", "READY ✅" if a2_done else "PENDING ⚪")
    m3.metric("Agent 03 (ETL Staging)", "READY ✅" if a3_done else "PENDING ⚪")
    m4.metric("Agent 04 (MDM Deploy)", "READY ✅" if a4_done else "PENDING ⚪")

# Agent 01 Output
with tab_a1:
    st.subheader("Parsed Requirements Artifacts")
    st.json({
        "page_id": page_id_input,
        "project_key": project_key_input,
        "jira_ui_key": getattr(state, "jira_ui_issue_key", None),
        "jira_etl_key": getattr(state, "jira_etl_issue_key", None),
        "jira_mdm_key": getattr(state, "jira_mdm_issue_key", None),
        "raw_specification": requirement_spec,
        "parsed_requirements": getattr(state, "jira_parsed_data", {}),
    })

# Agent 02 Output
with tab_a2:
    st.subheader("Generated Streamlit UI Code")
    ui_code = getattr(
        state, "ui_code", "# Agent 02 output will appear here after execution."
    )

    codespace_name = os.getenv("CODESPACE_NAME")
    port_forward_template = os.getenv("GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN")

    if codespace_name and port_forward_template:
        app_url = f"https://{codespace_name}-8502.{port_forward_template}"
    else:
        app_url = "http://localhost:8502"

    col_u1, col_u2 = st.columns([1, 3])
    with col_u1:
        if st.button("🚀 Start / Launch Existing UI App (Port 8502)", key="btn_launch_ui_direct"):
            with st.spinner("Connecting / Launching Streamlit Server on Port 8502..."):
                if ensure_ui_server_running(state, max_retries=3):
                    st.success("Server is online!")
                else:
                    st.error("Could not launch app. No valid `ui_code` in state.")

    with col_u2:
        is_live = ensure_ui_server_running(state, max_retries=1)
        if is_live:
            st.link_button("🌐 Open Active UI Application", app_url, use_container_width=True)
        else:
            st.info("ℹ️ UI App Server is offline. Click 'Start / Launch Existing UI App' or run Agent 02.")

    st.code(ui_code, language="python")

# Agent 03 Output
with tab_a3:
    st.subheader("Generated ETL Pipeline Code")
    etl_code = getattr(
        state, "etl_code", "# Agent 03 output will appear here after execution."
    )
    st.code(etl_code, language="python")

    st.divider()
    st.subheader("📊 Live DuckDB Staging Explorer & SQL Console (`cleansed_staging_data`)")
    duckdb_file = PROJECT_ROOT / "staging.duckdb"

    if duckdb_file.exists():
        try:
            duck_conn = duckdb.connect(str(duckdb_file), read_only=True)
            tables = duck_conn.execute("SHOW TABLES").fetchdf()

            if not tables.empty and "cleansed_staging_data" in tables["name"].values:
                duck_df = duck_conn.execute(
                    "SELECT * FROM cleansed_staging_data ORDER BY 1 DESC"
                ).fetchdf()
                st.caption(f"Showing {len(duck_df)} staging record(s) in DuckDB:")
                st.dataframe(duck_df, use_container_width=True)

                with st.expander("🔍 Run Custom DuckDB SQL Query", expanded=False):
                    custom_query = st.text_area(
                        "Enter SQL Query:",
                        value="SELECT count(*) as total_records, avg(credit_score) as avg_score FROM cleansed_staging_data",
                        height=100,
                    )
                    if st.button("Run SQL Query", key="btn_run_duck_sql"):
                        try:
                            res_df = duck_conn.execute(custom_query).fetchdf()
                            st.dataframe(res_df, use_container_width=True)
                        except Exception as q_err:
                            st.error(f"SQL Execution Error: {q_err}")
            else:
                st.info(
                    "DuckDB database exists, but table `cleansed_staging_data` has not"
                    " been created yet. Run Agent 03 to populate staging data."
                )
            duck_conn.close()
        except Exception as duck_err:
            st.error(f"DuckDB Connection / Query Error: {duck_err}")
    else:
        st.warning(
            "⚠️ No `staging.duckdb` file found at root. Run Agent 03 to generate the DuckDB staging database."
        )

# Agent 04 Output
with tab_a4:
    st.subheader("Generated PostgreSQL DDL")
    ddl_code = getattr(
        state,
        "mdm_ddl",
        "-- Agent 04 output will appear here after execution.",
    )
    st.code(ddl_code, language="sql")

    st.divider()
    st.subheader("Live PostgreSQL Query Results (`public.customer_master`)")

    pg_connection_string = os.getenv(
        "POSTGRES_CONNECTION_URI",
        "postgresql://postgres:postgres@localhost:5432/mdm_db",
    )
    is_local_pg = "localhost" in pg_connection_string or "127.0.0.1" in pg_connection_string

    postgres_ready = ensure_postgres_running("mdm-postgres") if is_local_pg else True

    if postgres_ready:
        try:
            conn = psycopg2.connect(pg_connection_string)
            df = pd.read_sql("SELECT * FROM public.customer_master;", conn)
            conn.close()
            st.dataframe(df, use_container_width=True)
        except Exception as e:
            st.error(f"PostgreSQL Connection / Query Error: {e}")
    else:
        st.error(
            "❌ Unable to auto-start PostgreSQL container. Please check Docker status."
        )