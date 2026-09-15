import ast
import os
import traceback
import logging
from pathlib import Path
import duckdb
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth
from pydantic import BaseModel, Field

from core.llm_factory import get_llm
from core.state import ProjectState

# Absolute path resolution to project root: /workspaces/codespaces-blank/sdlc-multiagent-automation
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Default seed records to ensure DuckDB has data preview immediately on first run
DEFAULT_SEED_PAYLOADS = [
    {
        "full_name": "Ananya Sharma",
        "email": "ananya.sharma@example.com",
        "phone": "+919876543210",
        "aadhaar_no": "123456789012",
        "pan_no": "ABCDE1234F",
        "credit_score": 750,
        "annual_income": 1200000,
    },
    {
        "full_name": "Rajesh Kumar",
        "email": "rajesh.k@example.com",
        "phone": "+919123456789",
        "aadhaar_no": "987654321098",
        "pan_no": "XYZPS5678G",
        "credit_score": 620,
        "annual_income": 650000,
    },
]


# region 1. JIRA SPEC FETCHER
# ============================================================================
# Section 1: Fetch Task Requirements from Jira REST API
# ============================================================================
def fetch_jira_etl_details(issue_key: str) -> str:
    """Fetches summary and description for an ETL Jira issue key."""
    if not issue_key:
        raise ValueError("No Jira issue key provided for ETL task.")

    atlassian_url = os.getenv("ATLASSIAN_URL", "https://shashankwv.atlassian.net").rstrip("/")
    url = f"{atlassian_url}/rest/api/3/issue/{issue_key}"

    auth = HTTPBasicAuth(
        os.getenv("ATLASSIAN_EMAIL") or os.getenv("JIRA_EMAIL"),
        os.getenv("ATLASSIAN_API_TOKEN") or os.getenv("JIRA_API_TOKEN"),
    )
    headers = {"Accept": "application/json"}

    response = requests.get(url, auth=auth, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(
            f"Failed to fetch Jira issue {issue_key}: {response.status_code} - {response.text}"
        )

    data = response.json()
    fields = data.get("fields", {})
    summary = fields.get("summary", "")

    description_raw = fields.get("description")
    description_text = ""
    if isinstance(description_raw, dict):
        content_blocks = description_raw.get("content", [])
        for block in content_blocks:
            for item in block.get("content", []):
                if item.get("type") == "text":
                    description_text += item.get("text", "") + " "
    elif isinstance(description_raw, str):
        description_text = description_raw

    return f"Jira Issue: {issue_key}\nSummary: {summary}\nDescription: {description_text.strip()}"
# endregion


# region 2. LLM PIPELINE BUILDER
# ============================================================================
# Section 2: Pydantic Schema & LLM Code Generation
# ============================================================================
class ETLPipelineResponse(BaseModel):
    etl_code: str = Field(
        description=(
            "Valid Python script containing transformations using DuckDB/Polars/Pandas. "
            "It must clean raw payloads, enforce string stripping, calculate risk metrics, "
            "and include `mask_aadhaar(aadhaar_str)`, `transform_batch(raw_records)`, and "
            "`process_and_store_kyc(form_data)` functions. Do NOT include markdown fences (```)."
        )
    )


def generate_etl_pipeline(jira_spec: str, existing_code: str = None) -> str:
    """Generates Python ETL transformation script based on Jira ticket specifications."""
    base_llm = get_llm()
    structured_llm = base_llm.with_structured_output(ETLPipelineResponse)

    context_prefix = ""
    if existing_code:
        context_prefix = f"# PREVIOUS ATTEMPT & DIAGNOSTICS:\n{existing_code}\n\n"

    prompt = f"""{context_prefix}You are an enterprise ETL Data Engineer.
Based on the following Jira task description, write modular Python transformation logic:

{jira_spec}

STRICT REQUIREMENTS:
1. Parse and sanitize raw incoming customer records.
2. Implement `mask_aadhaar(val)` keeping only the last 4 digits (e.g., 'XXXX-XXXX-1234').
3. Calculate `risk_index` float/int based on credit score or income metrics.
4. Provide `transform_batch(raw_records: list[dict]) -> list[dict]` that outputs cleansed dicts.
5. Provide `process_and_store_kyc(form_data: dict) -> dict` which transforms a single payload and inserts it into DuckDB table `cleansed_staging_data` inside `staging.duckdb` resolved relative to project root (`Path(__file__).resolve().parent / 'staging.duckdb'`), returning {{'status': 'success', 'message': '...'}}.
Return ONLY valid Python code."""

    response: ETLPipelineResponse = structured_llm.invoke(prompt)
    return response.etl_code
# endregion


# region 3. SELF-HEALING & DUCKDB RUNNER
# ============================================================================
# Section 3: Validation, Self-Healing Check, & Dynamic DuckDB Insertion
# ============================================================================
def validate_etl_code(code_str: str) -> tuple[bool, str, str]:
    """Validates syntax and required entrypoints in generated ETL script."""
    # AST Syntax Verification
    try:
        ast.parse(code_str)
    except SyntaxError as se:
        return False, "SyntaxError", f"Line {se.lineno}: {se.msg}"

    # Required Callables Check
    local_scope = {}
    try:
        exec(code_str, local_scope, local_scope)
    except Exception as e:
        return False, "Runtime Execution Error", f"{traceback.format_exc()}\nDetail: {e}"

    if "transform_batch" not in local_scope or not callable(local_scope["transform_batch"]):
        return False, "Missing Entrypoint", "Missing required function `transform_batch(raw_records)`"

    return True, "NONE", ""


def run_etl_in_duckdb(etl_code: str, raw_payloads: list[dict], db_filename: str = "staging.duckdb") -> dict:
    """Executes transformation script and dynamically inserts data into DuckDB with auto-schema evolution."""
    etl_script_path = PROJECT_ROOT / "etl_pipeline.py"

    # Persist code to project root for streamlit_app.py imports
    with open(etl_script_path, "w", encoding="utf-8") as f:
        f.write(etl_code)

    local_scope = {}
    exec(etl_code, local_scope, local_scope)
    transform_fn = local_scope["transform_batch"]

    cleansed_records = transform_fn(raw_payloads)
    if not cleansed_records:
        return {"status": "SUCCESS", "processed_count": 0, "sample_output": {}}

    db_path = PROJECT_ROOT / db_filename
    conn = duckdb.connect(str(db_path))
    df_new = pd.DataFrame(cleansed_records)

    # Dynamic schema handling & auto-evolution targeting 'cleansed_staging_data'
    tables = [t[0] for t in conn.execute("SHOW TABLES").fetchall()]
    if "cleansed_staging_data" not in tables:
        conn.register("temp_df", df_new)
        conn.execute("CREATE TABLE cleansed_staging_data AS SELECT * FROM temp_df")
    else:
        existing_cols = [c[0] for c in conn.execute("DESCRIBE cleansed_staging_data").fetchall()]
        for col in df_new.columns:
            if col not in existing_cols:
                col_type = "DOUBLE" if pd.api.types.is_numeric_dtype(df_new[col]) else "VARCHAR"
                conn.execute(f"ALTER TABLE cleansed_staging_data ADD COLUMN {col} {col_type}")

        conn.register("temp_df", df_new)
        conn.execute("INSERT INTO cleansed_staging_data SELECT * FROM temp_df")

    conn.close()

    return {
        "status": "SUCCESS",
        "processed_count": len(cleansed_records),
        "sample_output": cleansed_records[0],
    }
# endregion


# region 4. AGENT ORCHESTRATOR NODE
# ============================================================================
# Section 4: Main Agent Entrypoint with Self-Healing Feedback Loop
# ============================================================================
def run_etl_agent(state: ProjectState, raw_payloads: list[dict] = None) -> ProjectState:
    """Agent 03 Orchestrator: Validates, heals, and runs ETL pipeline against DuckDB."""
    logger.info("🤖 [Agent 03] Starting ETL Agent...")

    # Fetch spec from Jira API if issue key exists; otherwise fallback to state/confluence text
    if getattr(state, "jira_etl_issue_key", None):
        logger.info(f"Fetching Jira task details for key: {state.jira_etl_issue_key}")
        jira_spec = fetch_jira_etl_details(state.jira_etl_issue_key)
    else:
        jira_spec = (
            getattr(state, "jira_etl_task", None)
            or getattr(state, "raw_confluence_doc", None)
            or "Generate production KYC cleaning pipeline with Aadhaar masking and risk calculation into cleansed_staging_data."
        )

    # Self-Healing Retry Loop
    max_retries = 3
    etl_code = ""
    healing_context = None

    for attempt in range(1, max_retries + 1):
        logger.info(f"Generating ETL Pipeline (Attempt {attempt}/{max_retries})...")
        etl_code = generate_etl_pipeline(jira_spec, existing_code=healing_context)

        is_valid, err_type, err_traceback = validate_etl_code(etl_code)
        if is_valid:
            logger.info(f"✅ [SELF-HEALING SUCCESS] Valid ETL pipeline code generated on attempt #{attempt}!")
            break

        logger.warning(f"⚠️ [ETL VALIDATION ERROR]: {err_type}\n{err_traceback}")
        healing_context = f"# ERROR CATEGORY: {err_type}\n# TRACEBACK:\n{err_traceback}\n"

    state.etl_code = etl_code

    # Input payloads: fallback to seed payloads if state is empty
    input_payloads = raw_payloads or getattr(state, "raw_payloads", None) or DEFAULT_SEED_PAYLOADS

    logger.info(f"Executing ETL runner against DuckDB with {len(input_payloads)} record(s)...")
    result = run_etl_in_duckdb(state.etl_code, input_payloads)

    logger.info(f"✅ Agent 03 completed successfully. Processed {result['processed_count']} records.")
    return state
# endregion