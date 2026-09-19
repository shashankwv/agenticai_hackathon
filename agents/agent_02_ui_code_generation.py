import ast
import logging
import os
from pathlib import Path
import re
import shutil

from pydantic import BaseModel, Field
import requests
from requests.auth import HTTPBasicAuth

from core.llm_factory import get_llm
from core.state import ProjectState
from core.ui_server import restart_ui_server

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UI_DIR = PROJECT_ROOT / "ui"
UI_BACKUP_DIR = UI_DIR / "backup"
UI_CODE_PATH = UI_DIR / "streamlit_ui_code.py"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fetch_jira_ui_details(issue_key: str) -> str:
    if not issue_key:
        raise ValueError("No Jira issue key provided for UI task.")

    atlassian_url = os.getenv("ATLASSIAN_URL", "https://shashankwv.atlassian.net").rstrip("/")
    url = f"{atlassian_url}/rest/api/3/issue/{issue_key}"

    auth = HTTPBasicAuth(
        os.getenv("ATLASSIAN_EMAIL") or os.getenv("JIRA_EMAIL"),
        os.getenv("ATLASSIAN_API_TOKEN") or os.getenv("JIRA_API_TOKEN"),
    )
    headers = {"Accept": "application/json"}

    response = requests.get(url, auth=auth, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch Jira issue {issue_key}: {response.status_code}")

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


class UICodeResponse(BaseModel):
    ui_code: str = Field(description="Top-level Streamlit Python script code.")


def clean_llm_json_response(raw_resp) -> str:
    """Removes markdown code fences if present around JSON outputs, safely converting lists or objects to strings."""
    if isinstance(raw_resp, list):
        raw_resp = "".join(
            block.get("text", "") if isinstance(block, dict) else str(block) 
            for block in raw_resp
        )
    elif not isinstance(raw_resp, str):
        raw_resp = str(raw_resp)

    cleaned = raw_resp.strip()
    if cleaned.startswith("```json"):
        cleaned = cleaned[7:]
    elif cleaned.startswith("```"):
        cleaned = cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned[:-3]
    return cleaned.strip()


def generate_ui_code(jira_spec: str, existing_code: str = None, baseline_code: str = None) -> str:
    context = ""
    if existing_code:
        context += f"# FIX PREVIOUS ERROR:\n{existing_code}\n\n"
    if baseline_code:
        context += f"# PRESERVE BASELINE CODE:\n{baseline_code}\n\n"

    prompt = f"""{context}Build a Streamlit form based on:
{jira_spec}

REQUIREMENTS:
1. Import `re`, `json`, `streamlit as st`, `requests`.
2. Define `API_INGEST_URL = "http://127.0.0.1:8000/api/ingest"`.
3. Define helper:
def submit_to_pipeline(form_data: dict) -> dict:
    try:
        resp = requests.post(API_INGEST_URL, json=form_data, timeout=10)
        return resp.json()
    except Exception as e:
        return {{"status": "error", "message": f"Ingestion server offline (Port 8000). Please start api_bridge.py: {{e}}"}}

4. Use `st.form("kyc_form")` and submit with `submit_to_pipeline(form_data)`.
5. Show appropriate UI alerts:
   - status 'success': `st.success(...)`
   - status 'requires_pipeline' or 'requires_human_review': `st.info(...)` or `st.warning(...)`
   - status 'error': `st.error(...)`
6. Apply regex formatting for Aadhaar/PAN fields.
7. Return executable Python code wrapped ONLY inside valid structured JSON schema."""

    # Primary Attempt: Structured LLM Output
    try:
        structured_llm = get_llm(schema=UICodeResponse)
        response: UICodeResponse = structured_llm.invoke(prompt)
        if response and response.ui_code:
            return response.ui_code
    except Exception as e:
        logger.warning(f"Structured schema failed in Agent 02, attempting fallback parsing: {e}")

    # Fallback Attempt: Raw Text Prompting & Sanitization
    llm_raw = get_llm()
    raw_output = llm_raw.invoke(prompt)
    text_content = raw_output.content if hasattr(raw_output, "content") else raw_output

    cleaned_json = clean_llm_json_response(text_content)

    try:
        parsed = UICodeResponse.model_validate_json(cleaned_json)
        return parsed.ui_code
    except Exception:
        pass

    code_match = re.search(r"```(?:python|py)?\s*(.*?)\s*```", text_content if isinstance(text_content, str) else cleaned_json, re.DOTALL | re.IGNORECASE)
    if code_match:
        extracted = code_match.group(1).strip()
        if "st.form" in extracted or "submit_to_pipeline" in extracted:
            return extracted

    return cleaned_json


def validate_ui_code(code_str: str) -> tuple[bool, str, str]:
    try:
        ast.parse(code_str)
    except SyntaxError as se:
        return False, "SyntaxError", f"Line {se.lineno}: {se.msg}"

    if "submit_to_pipeline" not in code_str:
        return False, "Validation Error", "Missing submit_to_pipeline helper."
    if "st.form" not in code_str:
        return False, "Validation Error", "Missing st.form block."

    return True, "NONE", ""


def run_ui_code_generation_agent(state: ProjectState, reset: bool = False) -> ProjectState:
    logger.info("🤖 [Agent 02] Starting Fast UI Code Generation...")

    UI_DIR.mkdir(parents=True, exist_ok=True)
    UI_BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    if reset:
        state.ui_code = ""
        # Backup management for streamlit_ui_code.py
        backup_file = UI_BACKUP_DIR / "streamlit_ui_code.py"
        if backup_file.exists():
            backup_file.unlink()
            logger.info(f"Deleted old UI backup: {backup_file}")

        if UI_CODE_PATH.exists():
            shutil.copy2(UI_CODE_PATH, backup_file)
            logger.info(f"Backed up UI code from {UI_CODE_PATH} to {backup_file}")
            UI_CODE_PATH.unlink()
            logger.info(f"Deleted active UI file: {UI_CODE_PATH}")

    if getattr(state, "jira_ui_issue_key", None):
        jira_spec = fetch_jira_ui_details(state.jira_ui_issue_key)
    else:
        jira_spec = getattr(state, "jira_ui_task", None) or "Create onboarding KYC form with name, email, phone, aadhaar_no, pan_no."

    baseline_code = getattr(state, "ui_code", None) or None
    max_retries = 2
    healing_context = None
    ui_code = ""

    for attempt in range(1, max_retries + 1):
        ui_code = generate_ui_code(jira_spec, existing_code=healing_context, baseline_code=baseline_code)
        is_valid, err_type, err_msg = validate_ui_code(ui_code)
        if is_valid:
            break
        healing_context = f"{err_type}: {err_msg}"

    with open(UI_CODE_PATH, "w", encoding="utf-8") as f:
        f.write(ui_code)

    state.ui_code = ui_code
    restart_ui_server(port=8502)
    return state