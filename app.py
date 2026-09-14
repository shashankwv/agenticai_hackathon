import json
import os
from pathlib import Path

import duckdb
import pandas as pd
import psycopg2
import streamlit as st

# Import State and Agents
from agents.agent_01_requirements.step_04_agent import run_requirements_agent
from agents.agent_02_ui_code_generation.step_03_agent import (
    run_ui_code_generation_agent,
)
from agents.agent_03_etl.step_04_agent import run_etl_agent
from agents.agent_04_mdm.step_03_agent import run_mdm_agent_autonomous
from agents.agent_04_mdm.step_05_postgres_executor import (
    ensure_postgres_running,
)
from core.state import ProjectState

# --- ABSOLUTE PATH RESOLUTION ---
PROJECT_ROOT = Path(__file__).resolve().parent
CHECKPOINT_PATH = PROJECT_ROOT / "state_checkpoint_1.json"


# --- HELPER FUNCTIONS FOR STATE PERSISTENCE ---
def load_checkpoint(filepath: Path = CHECKPOINT_PATH) -> ProjectState:
    """Loads ProjectState from disk if the file exists."""
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return ProjectState(**data)
    return ProjectState()


def save_checkpoint(
    state: ProjectState, filepath: Path = CHECKPOINT_PATH
) -> None:
    """Saves current ProjectState to disk as a JSON checkpoint."""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(state.model_dump_json(indent=2))
    st.toast(f"💾 Checkpoint saved to {filepath.name}!")


# --- STREAMLIT CONFIGURATION & STYLING ---
st.set_page_config(
    page_title="Autonomous SDLC Agentic Dashboard", page_icon="🤖", layout="wide"
)

st.markdown(
    """
<style>
    /* App Base Background */
    .stApp {
        background-color: #0E1117;
        color: #E0E6ED;
    }
    
    /* Headers */
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
    
    /* Input and Textarea Backgrounds & High-Contrast Readable Text */
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

    /* Sidebar Input Text Fields */
    section[data-testid="stSidebar"] input,
    section[data-testid="stSidebar"] textarea {
        color: #0F172A !important;
        -webkit-text-fill-color: #0F172A !important;
        background-color: #F1F5F9 !important;
    }

    /* Expander Container styling */
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

    /* Base Buttons */
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

    /* Primary Action Buttons */
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

# --- SESSION STATE INITIALIZATION ---
if "project_state" not in st.session_state:
    st.session_state.project_state = load_checkpoint()

state = st.session_state.project_state

# --- HEADER SECTION ---
st.markdown(
    '<div class="main-header">🤖 Autonomous Agentic SDLC & MDM Engine</div>',
    unsafe_allow_html=True,
)
st.markdown(
    '<div class="sub-header">Decoupled Multi-Agent Pipeline with Real-Time'
    ' State Persistence</div>',
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

if st.sidebar.button(
    "🔄 Sync State from Checkpoint File", use_container_width=True
):
    st.session_state.project_state = load_checkpoint()
    st.toast("✅ Session state updated from state_checkpoint_1.json!")
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
        save_checkpoint(state)

        status_container.info("🔄 [2/4] Executing Agent 02 (UI Generation)...")
        state = run_ui_code_generation_agent(state)
        save_checkpoint(state)

        status_container.info("🔄 [3/4] Executing Agent 03 (ETL Pipeline)...")
        state = run_etl_agent(state)
        save_checkpoint(state)

        status_container.info(
            "🔄 [4/4] Executing Agent 04/05 (MDM & Postgres)..."
        )
        state = run_mdm_agent_autonomous(state, execute_live=execute_live)
        save_checkpoint(state)

    status_container.success(
        "🎉 Full Pipeline Executed & All Checkpoints Saved!"
    )
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
            save_checkpoint(state)
            st.session_state.project_state = state
        st.toast("Agent 01 Execution Completed!")
        st.rerun()

with col_a2:
    st.markdown("**Agent 02: UI Generator**")
    if st.button("Run Agent 02", key="btn_a2", use_container_width=True):
        with st.status("🚀 Launching Vite Dev Server...", expanded=True) as status_box:
            st.write("Fetching Jira task details & generating React TSX code...")
            st.write("Stopping existing Vite instances...")
            st.write("Writing updated TSX to frontend-ui/src/App.tsx...")
            
            state = run_ui_code_generation_agent(state)
            save_checkpoint(state)
            st.session_state.project_state = state
            
            st.write(f"Server live at: {getattr(state, 'ui_sandbox_url', 'N/A')}")
            status_box.update(label="✅ Vite Server Restarted & Ready!", state="complete")
        st.toast("Agent 02 Execution Completed!")
        st.rerun()

with col_a3:
    st.markdown("**Agent 03: ETL Engine**")
    if st.button("Run Agent 03", key="btn_a3", use_container_width=True):
        with st.spinner("Generating & Running Staging ETL..."):
            state = run_etl_agent(state)
            save_checkpoint(state)
            st.session_state.project_state = state
        st.toast("Agent 03 Execution Completed!")
        st.rerun()

with col_a4:
    st.markdown("**Agent 04/05: MDM Target DB**")
    if st.button("Run Agent 04/05", key="btn_a4", use_container_width=True):
        with st.spinner("Validating DDL & Executing on Postgres..."):
            state = run_mdm_agent_autonomous(state, execute_live=execute_live)
            save_checkpoint(state)
            st.session_state.project_state = state
        st.toast("Agent 04/05 Execution Completed!")
        st.rerun()

st.divider()

# --- STATE INSPECTOR & MANUAL EDITOR SECTION ---
st.markdown("### 🔍 Live ProjectState Inspector & Editor")

with st.expander("✏️ Edit Session State Variables Directly", expanded=False):
    st.markdown(
        "Modify any state variable directly in the JSON payload below and click"
        " **Apply & Save State Changes**."
    )

    with st.form("edit_state_form"):
        raw_json_input = st.text_area(
            "JSON State Payload",
            value=state.model_dump_json(indent=2),
            height=300,
        )

        submit_changes = st.form_submit_button(
            "💾 Apply & Save State Changes", type="primary"
        )

        if submit_changes:
            try:
                updated_dict = json.loads(raw_json_input)
                st.session_state.project_state = ProjectState(**updated_dict)
                save_checkpoint(st.session_state.project_state)

                st.success("✅ State successfully updated and saved to file!")
                st.rerun()
            except Exception as e:
                st.error(f"❌ Invalid JSON structure or state payload: {e}")

st.divider()

# --- MAIN DASHBOARD OUTPUT TABS ---
tab_summary, tab_a1, tab_a2, tab_a3, tab_a4 = st.tabs([
    "📊 Pipeline Status",
    "📋 Agent 01: Requirements Spec",
    "🖥️ Agent 02: Generated UI Code",
    "⚙️ Agent 03: ETL Code",
    "🗄️ Agent 04/05: MDM & PostgreSQL",
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
    m4.metric("Agent 04/05 (MDM Deploy)", "READY ✅" if a4_done else "PENDING ⚪")

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
    st.subheader("Generated React/TypeScript UI Frontend Code")
    ui_code = getattr(
        state, "ui_code", "# Agent 02 output will appear here after execution."
    )

    sandbox_url = getattr(state, "ui_sandbox_url", None)
    if sandbox_url:
        st.success(f"🚀 **Vite Dev Server Active**: {sandbox_url}")
        st.link_button("🚀 Open Generated App Sandbox", sandbox_url)

    st.code(ui_code, language="typescript")

# Agent 03 Output
with tab_a3:
    st.subheader("Generated ETL Pipeline Code")
    etl_code = getattr(
        state, "etl_code", "# Agent 03 output will appear here after execution."
    )
    st.code(etl_code, language="python")

    st.divider()
    st.subheader("Live DuckDB Staging Query Results (`cleansed_staging_data`)")
    duckdb_file = PROJECT_ROOT / "staging.duckdb"

    if duckdb_file.exists():
        try:
            duck_conn = duckdb.connect(str(duckdb_file), read_only=True)
            tables = duck_conn.execute("SHOW TABLES").fetchdf()

            if not tables.empty and "cleansed_staging_data" in tables["name"].values:
                duck_df = duck_conn.execute(
                    "SELECT * FROM cleansed_staging_data"
                ).fetchdf()
                st.caption(f"Showing {len(duck_df)} staging record(s) in DuckDB:")
                st.dataframe(duck_df, use_container_width=True)
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
            "⚠️ No `staging.duckdb` file found. Run Agent 03 to generate the DuckDB"
            " staging database."
        )

# Agent 04/05 Output
with tab_a4:
    st.subheader("Generated PostgreSQL DDL")
    ddl_code = getattr(
        state,
        "mdm_ddl",
        "-- Agent 04/05 output will appear here after execution.",
    )
    st.code(ddl_code, language="sql")

    st.divider()
    st.subheader("Live PostgreSQL Query Results (`public.customer_master`)")

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
            st.error(f"PostgreSQL Connection / Query Error: {e}")
    else:
        st.error(
            "❌ Unable to auto-start PostgreSQL container. Please check Docker"
            " status."
        )