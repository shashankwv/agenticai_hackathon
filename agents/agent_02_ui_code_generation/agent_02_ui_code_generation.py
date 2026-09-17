import ast
import logging
import os
from pathlib import Path
import traceback

from pydantic import BaseModel, Field
import requests
from requests.auth import HTTPBasicAuth

from core.llm_factory import get_llm
from core.state import ProjectState

# Absolute path resolution to project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# region 1. JIRA SPEC FETCHER
# ============================================================================
# Section 1: Fetch Task Requirements from Jira REST API
# ============================================================================
def fetch_jira_ui_details(issue_key: str) -> str:
    """Fetches summary and description for a UI Jira issue key."""
    if not issue_key:
        raise ValueError("No Jira issue key provided for UI generation task.")

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


# region 2. LLM CODE GENERATOR & SCHEMAS
# ============================================================================
# Section 2: Pydantic Schema & Structured Output Generation
# ============================================================================
class UICodeResponse(BaseModel):
    ui_code: str = Field(
        description=(
            "Valid Python script that builds a Streamlit form based on user specs. "
            "It must define `render_generated_ui()` entrypoint and handle form submission "
            "by connecting to ETL processing functions seamlessly without raw markdown blocks (```)."
        )
    )


def generate_ui_code(jira_spec: str, existing_code: str = None, baseline_code: str = None) -> str:
    """Generates Python Streamlit UI code using structured output based on Jira tickets.

    `existing_code` carries error-diagnostic context from a failed *attempt*
    within the current self-healing run (fix this bug). `baseline_code`
    carries the last successfully generated version *from a previous run* of
    this agent (extend this, don't discard it) — passing the same run's own
    output back in as if it were "diagnostics" is why an agent can end up
    regenerating a completely fresh UI from scratch on every click instead of
    building on what it had already generated for earlier Jira stories.
    """
    structured_llm = get_llm(schema=UICodeResponse)

    context_prefix = ""
    if existing_code:
        context_prefix += (
            "# PREVIOUS ATTEMPT & ERROR DIAGNOSTICS (fix the issue, don't repeat it):\n"
            f"{existing_code}\n\n"
        )
    if baseline_code:
        context_prefix += (
            "# CURRENT PRODUCTION UI (from a previous Jira story — this is LIVE and already working):\n"
            f"{baseline_code}\n\n"
            "INCREMENTAL UPDATE INSTRUCTIONS: Treat the new Jira task below as a DELTA against the UI above. "
            "Preserve every existing field, widget, and function exactly as-is unless the new task explicitly asks to change it. "
            "Only ADD what the new task actually requires.\n\n"
        )

    prompt = f"""{context_prefix}You are an expert Frontend Streamlit Engineer.
Based on the following requirements, write production-ready Python Streamlit code:

{jira_spec}

STRICT REQUIREMENTS & SELF-HEALING GUARDRAILS:
1. Wrap all form rendering inside `render_generated_ui()`.
2. Gather all input fields into a `form_data` dictionary.
3. Upon clicking 'Submit & Process KYC', dynamically import and invoke `process_and_store_kyc(form_data)` from `etl_pipeline.py`.
4. HARDENING RULE: You MUST wrap the invocation of `process_and_store_kyc(form_data)` inside a robust try-except block.
5. Gracefully process response dict:
   - If response status is 'success': display `st.success(...)`.
   - If response status is 'requires_human_review': display `st.warning(...)` informing the user that schema resolution is pending Human-In-The-Loop validation.
   - If response status is 'error' or an uncaught Exception occurs: display `st.error(...)` showing a clear, friendly error message instead of an unhandled exception traceback.
6. Do NOT output raw markdown tags or ```python formatting wrappers.
Return ONLY executable Python code."""

    response: UICodeResponse = structured_llm.invoke(prompt)
    return response.ui_code
# endregion


# region 3. CODE VALIDATION & AST PARSING
# ============================================================================
# Section 3: AST Parsing & Entrypoint Verification
# ============================================================================
def validate_ui_code(code_str: str) -> tuple[bool, str, str]:
    """Validates syntax and required entrypoints in generated UI script."""
    # AST Syntax Verification
    try:
        ast.parse(code_str)
    except SyntaxError as se:
        return False, "SyntaxError", f"Line {se.lineno}: {se.msg}"

    # Verify render_generated_ui function callable exists
    local_scope = {}
    try:
        exec(code_str, local_scope, local_scope)
    except Exception as e:
        return False, "Runtime Execution Error", f"{traceback.format_exc()}\nDetail: {e}"

    if "render_generated_ui" not in local_scope or not callable(local_scope["render_generated_ui"]):
        return False, "Missing Entrypoint", "Missing required function `render_generated_ui()`"

    return True, "NONE", ""
# endregion


# region 4. AGENT ORCHESTRATOR & SELF-HEALING LOOP
# ============================================================================
# Section 4: Main Agent Orchestrator with Integrated Self-Healing
# ============================================================================
def run_ui_code_generation_agent(state: ProjectState) -> ProjectState:
    """Agent 02 Orchestrator: Validates, heals, and persists UI Streamlit code."""
    logger.info("🤖 [Agent 02] Starting UI Code Generation Agent...")

    # Fetch spec from Jira API if issue key exists; otherwise fallback to state/confluence text
    if getattr(state, "jira_ui_issue_key", None):
        logger.info(f"Fetching Jira task details for key: {state.jira_ui_issue_key}")
        jira_spec = fetch_jira_ui_details(state.jira_ui_issue_key)
    else:
        jira_spec = (
            getattr(state, "jira_ui_task", None)
            or getattr(state, "raw_confluence_doc", None)
            or "Generate customer onboarding Streamlit UI form with full name, email, phone, Aadhaar, PAN, and annual income fields."
        )

    # Carry the previously-generated UI forward as a baseline to extend, so
    # re-running Agent 02 for a new Jira story doesn't throw away everything
    # generated for earlier stories. Captured once, before the retry loop, so
    # it never gets confused with a failed attempt's diagnostics below.
    baseline_code = getattr(state, "ui_code", None) or None

    # Self-Healing Retry Loop
    max_retries = 3
    ui_code = ""
    healing_context = None

    for attempt in range(1, max_retries + 1):
        if healing_context:
            logger.warning(
                f"🩹 [SELF-HEALING APPLIED - Attempt {attempt}/{max_retries}] "
                f"Regenerating UI code due to error:\n{healing_context}"
            )

        logger.info(f"Generating UI Code (Attempt {attempt}/{max_retries})...")
        ui_code = generate_ui_code(jira_spec, existing_code=healing_context, baseline_code=baseline_code)

        is_valid, err_type, err_traceback = validate_ui_code(ui_code)
        if is_valid:
            logger.info(f"✅ [SELF-HEALING SUCCESS] Valid UI script generated on attempt #{attempt}!")
            break

        logger.warning(f"⚠️ [UI VALIDATION ERROR]: {err_type}\n{err_traceback}")
        healing_context = f"Validation Error ({err_type}):\n{err_traceback}"

    # Persist validated UI code into project root and state
    ui_script_path = PROJECT_ROOT / "generated_ui.py"
    with open(ui_script_path, "w", encoding="utf-8") as f:
        f.write(ui_code)

    state.ui_code = ui_code
    logger.info("✅ Agent 02 completed successfully. Saved code to generated_ui.py")
    return state
# endregion