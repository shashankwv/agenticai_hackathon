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

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def fetch_jira_etl_details(issue_key: str) -> str:
    """Fetches business criteria directly from Jira issue."""
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
        raise RuntimeError(
            f"Failed Jira API call for issue {issue_key}: {response.status_code}"
        )

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
    """Extracts plain string content from LLM response structure safely."""
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

    code_str = re.sub(
        r"^```(?:python|py)?\s*", "", code_str, flags=re.IGNORECASE
    )
    code_str = re.sub(r"\s*```$", "", code_str)

    lines = code_str.splitlines()
    cleaned_lines = []
    for line in lines:
        if line.endswith("\\") and (
            line.rstrip("\\").endswith('"') or line.rstrip("\\").endswith("'")
        ):
            line = line.rstrip("\\")
        cleaned_lines.append(line)

    return "\n".join(cleaned_lines)


def generate_etl_pipeline_fast(jira_spec: str, error_context: str = None) -> str:
    fix_prompt = (
        f"\nCRITICAL PREVIOUS EXECUTION ERROR TO FIX:\n{error_context}\n"
        "STRICT RULE: Do NOT include 'CURRENT_TIMESTAMP' or 'staged_at' anywhere in generated SQL statements or parameter lists. Rely entirely on DEFAULT CURRENT_TIMESTAMP defined on table creation.\n"
        if error_context
        else ""
    )

    prompt = f"""You are an Autonomous ETL Engineer aligned with Jira Business Requirements. Analyze the requirements specification and generate a self-contained Python ETL pipeline script.

Business Criteria / Jira Specification:
{jira_spec}
{fix_prompt}

DYNAMIC DESIGN REQUIREMENTS:
1. Output MUST be executable Python under 120 lines. No verbose docstrings. Include detailed logging/print statements for execution logs.
2. Imports: `json`, `uuid`, `re`, `duckdb`, `logging`, `pandas as pd`, `pathlib.Path`, `sys`.
3. Configure logging to stdout (`logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")`).
4. Locate DuckDB at `Path(__file__).resolve().parent / "etl.duckdb"`.
5. Implement `mask_sensitive_value(val: str, keep_last: int = 4) -> str` to dynamically mask sensitive string fields. Preserve already masked values (containing '*').
6. Fully Dynamic Field & Schema Handling (NO HARDCODED FIELD NAMES):
   - Dynamically iterate through all keys present in incoming payload JSON dictionaries.
   - Safely handle missing/null/None/empty string values for ANY arbitrary attribute by setting value to None (SQL NULL).
   - Normalize string fields dynamically (e.g. stripping spaces, stripping non-digits for phone/SSN before validation checks).
   - Use permissive validation checks (e.g. allow 9 digits OR masked strings for SSN, allow non-empty values for names).
   - Include clear, descriptive reason codes stating expected formats (e.g., 'INVALID_SSN_EXPECTED_9_DIGITS_OR_MASKED_FORMAT') when validation fails.
   - Dynamically identify sensitive fields (e.g. matching 'ssn', 'tax_id', 'secret', 'password', 'token') and apply `mask_sensitive_value`.
7. Implement `transform_batch(raw_records: list[dict]) -> tuple[list[dict], list[dict]]`:
   - Returns `(valid_records, rejected_records)`.
   - Ensure unique primary key UUIDs using `uuid.uuid4()` if primary key ('id') is missing or invalid.
8. Implement `run_pipeline()`:
   - Connect to `etl.duckdb`.
   - Ensure `landing_ui` exists: "CREATE TABLE IF NOT EXISTS landing_ui (id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid(), ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, payload JSON);"
   - Read JSON payloads from `landing_ui`.
   - Run `transform_batch(raw_records)`.
   - DYNAMIC COLUMN UNNESTING & UPSERT IN STAGING_UI:
     - Ensure table `staging_ui` exists: "CREATE TABLE IF NOT EXISTS staging_ui (id VARCHAR PRIMARY KEY, staged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);"
     - Collect all dynamic payload field keys across valid records (excluding 'id' and 'staged_at').
     - Check missing columns in `staging_ui` and run `ALTER TABLE staging_ui ADD COLUMN "key" VARCHAR` for each missing key.
     - Build dynamic UPSERT SQL and positional parameter bindings STRICTLY omitting `staged_at` and `CURRENT_TIMESTAMP`:
       
       all_keys = sorted(list(set(k for r in valid_records for k in r.keys() if k not in ('id', 'staged_at'))))
       cols = ['id'] + all_keys
       quoted_cols = ['"' + c + '"' for c in cols]
       placeholders = ['?'] * len(cols)
       update_set = ['"' + k + '"=EXCLUDED."' + k + '"' for k in all_keys]
       
       if update_set:
           sql = "INSERT INTO staging_ui (" + ", ".join(quoted_cols) + ") VALUES (" + ", ".join(placeholders) + ") ON CONFLICT (id) DO UPDATE SET " + ", ".join(update_set)
       else:
           sql = "INSERT INTO staging_ui (id) VALUES (?) ON CONFLICT (id) DO NOTHING"
           
       params = [[r.get('id')] + [r.get(k) for k in all_keys] for r in valid_records]
       con.executemany(sql, params)

   - Print a clean JSON summary object containing total counts (`landing`, `loaded`, `rejected`) and list of `rejected` records to stdout.
9. Standard entrypoint: `if __name__ == "__main__": run_pipeline()`.

Return ONLY valid executable Python code in a ```python ``` code block."""

    llm = get_llm(temperature=0.1)
    raw_output = llm.invoke(prompt)

    text_content = _normalize_llm_output_to_string(raw_output)

    match = re.search(
        r"```(?:python)?\s*(.*?)\s*```",
        text_content,
        re.DOTALL | re.IGNORECASE,
    )
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

    if (
        "transform_batch" not in cleaned_code
        or "run_pipeline" not in cleaned_code
    ):
        return (
            False,
            "ValidationError",
            "Missing required functions 'transform_batch' or 'run_pipeline'.",
        )

    return True, "NONE", ""


def run_etl_agent(
    state: ProjectState, reset: bool = False, max_retries: int = 3
) -> ProjectState:
    logger.info(
        "⚡ [Agent 03] Executing Dynamic Fast ETL Pipeline Initialization..."
    )

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
            logger.warning(
                f"Could not fetch Jira key {state.jira_etl_issue_key}: {e}"
            )
            jira_spec = state.jira_etl_task
    else:
        jira_spec = state.jira_etl_task

    if not jira_spec:
        raise ValueError(
            "No Jira specification or task context found in ProjectState for Agent 03."
        )

    etl_code = ""
    error_context = None
    is_valid = False

    for attempt in range(1, max_retries + 1):
        etl_code = generate_etl_pipeline_fast(
            jira_spec, error_context=error_context
        )
        is_valid, err_type, err_msg = validate_etl_code(etl_code)

        if is_valid:
            logger.info(
                f"✅ ETL code validated successfully on attempt {attempt}"
            )
            break

        logger.warning(
            f"⚠️ Attempt {attempt} failed [{err_type}]: {err_msg}. Retrying..."
        )
        error_context = f"{err_type}: {err_msg}"

    if not is_valid:
        raise RuntimeError(
            f"Generated ETL code failed validation after retries: {error_context}"
        )

    final_clean_code = sanitize_etl_code(etl_code)
    state.etl_code = final_clean_code
    etl_script_path = ETL_DIR / "etl_pipeline.py"
    with open(etl_script_path, "w", encoding="utf-8") as f:
        f.write(final_clean_code)

    return state