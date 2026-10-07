import ast
import logging
import os
from pathlib import Path
import re
import shutil

import duckdb
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth

from core.llm_factory import get_llm
from core.state import ProjectState

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ETL_DIR = PROJECT_ROOT / "etl"
ETL_BACKUP_DIR = ETL_DIR / "backup"
DUCKDB_PATH = ETL_DIR / "etl.duckdb"
LEGACY_DUCKDB_PATH = PROJECT_ROOT / "staging.duckdb"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_jira_etl_details(issue_key: str) -> str:
    if not issue_key:
        raise ValueError("No Jira issue key provided.")

    atlassian_url = os.getenv("ATLASSIAN_URL", "").rstrip("/")
    url = f"{atlassian_url}/rest/api/3/issue/{issue_key}"

    auth = HTTPBasicAuth(
        os.getenv("ATLASSIAN_EMAIL") or os.getenv("JIRA_EMAIL"),
        os.getenv("ATLASSIAN_API_TOKEN") or os.getenv("JIRA_API_TOKEN"),
    )
    headers = {"Accept": "application/json"}

    response = requests.get(url, auth=auth, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(f"Failed Jira API call for issue {issue_key}: {response.status_code}")

    data = response.json()
    fields = data.get("fields", {})
    summary = fields.get("summary", "")
    description_raw = fields.get("description", "")
    
    description_text = ""
    if isinstance(description_raw, dict):
        for block in description_raw.get("content", []):
            for item in block.get("content", []):
                if item.get("type") == "text":
                    description_text += item.get("text", "") + " "
    elif isinstance(description_raw, str):
        description_text = description_raw

    return f"Summary: {summary}\nDescription: {description_text.strip()}"


def _normalize_llm_output_to_string(raw_output) -> str:
    """Extracts plain string content from any LLM response structure safely."""
    if hasattr(raw_output, "content"):
        content = raw_output.content
    else:
        content = raw_output

    if isinstance(content, list):
        text_parts = []
        for block in content:
            if isinstance(block, dict):
                text_parts.append(block.get("text", ""))
            elif hasattr(block, "text"):
                text_parts.append(getattr(block, "text", ""))
            else:
                text_parts.append(str(block))
        return "".join(text_parts).strip()
    elif isinstance(content, dict):
        return content.get("text", str(content)).strip()
    
    return str(content).strip()


def sanitize_etl_code(code_str: str) -> str:
    """Cleans markdown wrappers and trailing syntax artifacts."""
    if not code_str:
        return ""

    code_str = re.sub(r"^```(?:python|py)?\s*", "", code_str, flags=re.IGNORECASE)
    code_str = re.sub(r"\s*```$", "", code_str)

    lines = code_str.splitlines()
    cleaned_lines = []
    for line in lines:
        if line.endswith("\\") and (line.rstrip("\\").endswith('"') or line.rstrip("\\").endswith("'")):
            line = line.rstrip("\\")
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def generate_etl_pipeline_fast(jira_spec: str, error_context: str = None) -> str:
    fix_prompt = f"\nPREVIOUS SYNTAX ERROR TO FIX:\n{error_context}\nKeep the code concise.\n" if error_context else ""

    prompt = f"""You are an Autonomous ETL Engineer. Analyze the requirements specification and generate a self-contained Python ETL pipeline script.

Specification:
{jira_spec}
{fix_prompt}

DYNAMIC DESIGN REQUIREMENTS:
1. Output MUST be executable Python under 100 lines. No verbose docstrings.
2. Imports: `json`, `uuid`, `re`, `duckdb`, `pandas as pd`, `pathlib.Path`.
3. Locate DuckDB at `Path(__file__).resolve().parent / "etl.duckdb"`.
4. Implement `mask_sensitive_value(val: str, keep_last: int = 4) -> str` to dynamically mask sensitive string fields.
5. Autonomous Field Normalization & Validation:
   - Infer identifier or sensitive payload key names dynamically based on the input payload/spec (e.g. matching fields ending in '_no', 'ssn', 'pan', 'aadhaar', 'id_number').
   - Clean raw values by extracting digits/alphanumerics (`re.sub(r'\\D', '', val)`).
   - If a record fails expected length or format checks for the identified domain field, reject it.
   - For rejected records, log the exact record ID, reason key, AND provide a clear expected sample string format (e.g., `expected_sample="XXX-XX-XXXX"` or standard layout).
6. Implement `transform_batch(raw_records: list[dict]) -> tuple[list[dict], list[dict]]`:
   - Returns `(valid_records, rejected_records)`.
   - Dynamically ensure unique primary key UUIDs using `uuid.uuid4()` if missing or placeholder strings are present.
7. Implement `run_pipeline()` to:
   - Connect to `etl.duckdb`.
   - Ensure table `landing_ui` exists: "CREATE TABLE IF NOT EXISTS landing_ui (id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid(), ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, payload JSON);"
   - Query raw payload JSON from `landing_ui`.
   - Execute `transform_batch()`.
   - Persist valid transformed records into `staging_ui`.
   - Output an execution summary including counts (landing, loaded, rejected) and detailed logs for any rejected items with expected sample guidance.
8. Standard entrypoint: `if __name__ == "__main__": run_pipeline()`.
9. SYNTAX SAFETY:
   - Use standard single-line strings for SQL queries.
   - Do NOT split strings or statements across lines without parentheses.

Return ONLY valid executable Python code in a ```python ``` code block."""

    llm = get_llm(temperature=0.1)
    raw_output = llm.invoke(prompt)
    
    text_content = _normalize_llm_output_to_string(raw_output)

    match = re.search(r"```(?:python)?\s*(.*?)\s*```", text_content, re.DOTALL | re.IGNORECASE)
    if match:
        extracted_code = match.group(1).strip()
    else:
        extracted_code = text_content.strip()

    return sanitize_etl_code(extracted_code)


def validate_etl_code(code_str: str) -> tuple[bool, str, str]:
    cleaned_code = sanitize_etl_code(code_str)
    try:
        ast.parse(cleaned_code)
    except SyntaxError as se:
        return False, "SyntaxError", f"Line {se.lineno}: {se.msg}"

    if "transform_batch" not in cleaned_code or "run_pipeline" not in cleaned_code:
        return False, "ValidationError", "Missing required functions 'transform_batch' or 'run_pipeline'."

    return True, "NONE", ""


def run_etl_agent(state: ProjectState, reset: bool = False, max_retries: int = 3) -> ProjectState:
    logger.info("⚡ [Agent 03] Executing Dynamic Fast ETL Pipeline Initialization...")

    ETL_DIR.mkdir(parents=True, exist_ok=True)
    ETL_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    if reset:
        if LEGACY_DUCKDB_PATH.exists():
            LEGACY_DUCKDB_PATH.unlink()
        backup_db = ETL_BACKUP_DIR / "etl.duckdb"
        if backup_db.exists():
            backup_db.unlink()
        if DUCKDB_PATH.exists():
            shutil.copy2(DUCKDB_PATH, backup_db)
            DUCKDB_PATH.unlink()

    if getattr(state, "jira_etl_issue_key", None):
        try:
            jira_spec = fetch_jira_etl_details(state.jira_etl_issue_key)
        except Exception as e:
            logger.warning(f"Could not fetch Jira key {state.jira_etl_issue_key}: {e}")
            jira_spec = state.jira_etl_task
    else:
        jira_spec = state.jira_etl_task

    if not jira_spec:
        raise ValueError("No Jira specification or task context found in ProjectState for Agent 03.")

    etl_code = ""
    error_context = None
    is_valid = False

    for attempt in range(1, max_retries + 1):
        etl_code = generate_etl_pipeline_fast(jira_spec, error_context=error_context)
        is_valid, err_type, err_msg = validate_etl_code(etl_code)

        if is_valid:
            logger.info(f"✅ ETL code validated successfully on attempt {attempt}")
            break

        logger.warning(f"⚠️ Attempt {attempt} failed [{err_type}]: {err_msg}. Retrying...")
        error_context = f"{err_type}: {err_msg}"

    if not is_valid:
        raise RuntimeError(f"Generated ETL code failed validation after retries: {error_context}")

    final_clean_code = sanitize_etl_code(etl_code)
    state.etl_code = final_clean_code
    etl_script_path = ETL_DIR / "etl_pipeline.py"
    with open(etl_script_path, "w", encoding="utf-8") as f:
        f.write(final_clean_code)

    return state