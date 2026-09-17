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


def fetch_existing_duckdb_schema(db_filename: str = "staging.duckdb") -> list[tuple[str, str]]:
    """Returns [(column_name, column_type), ...] for the live
    `cleansed_staging_data` table, or [] if it doesn't exist yet / the file
    is unreachable. Mirrors Agent 04's
    `fetch_existing_customer_master_schema` — the live table is the real
    source of truth for "what fields already exist", not whatever code
    string happened to be cached in session state from a previous run
    (which could be stale, or simply absent in a fresh session)."""
    db_path = Path(db_filename)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_filename
    if not db_path.exists():
        return []
    try:
        conn = duckdb.connect(str(db_path), read_only=True)
        try:
            tables = [t[0] for t in conn.execute("SHOW TABLES").fetchall()]
            if "cleansed_staging_data" not in tables:
                return []
            return [(c[0], c[1]) for c in conn.execute("DESCRIBE cleansed_staging_data").fetchall()]
        finally:
            conn.close()
    except Exception:
        return []


def generate_etl_pipeline(
    jira_spec: str,
    existing_code: str = None,
    baseline_code: str = None,
    existing_schema: list[tuple[str, str]] = None,
) -> str:
    """Generates Python ETL transformation script based on Jira ticket specifications.

    `existing_code` carries error-diagnostic context from a failed *attempt*
    within the current self-healing run (fix this bug). `baseline_code`
    carries the last successfully generated version *from a previous run* of
    this agent (extend this, don't discard it) — passing the same run's own
    output back in as if it were "diagnostics" was why Agent 03 regenerated
    a completely fresh pipeline from scratch on every click instead of
    building on what it had already generated for earlier Jira stories.
    `existing_schema` is the LIVE DuckDB table's actual current columns
    (mirrors Agent 04's live-schema introspection) — the authoritative
    signal for "what fields must keep working", independent of whatever
    code string is or isn't cached in session state.
    """
    structured_llm = get_llm(schema=ETLPipelineResponse)

    context_prefix = ""
    if existing_code:
        context_prefix += f"# PREVIOUS ATTEMPT & DIAGNOSTICS (fix the issue, don't repeat it):\n{existing_code}\n\n"
    if baseline_code:
        context_prefix += (
            "# CURRENT PRODUCTION PIPELINE (from a previous Jira story — this is "
            "LIVE and already working):\n"
            f"{baseline_code}\n\n"
            "INCREMENTAL UPDATE INSTRUCTIONS: Treat the new Jira task below as a "
            "DELTA against the pipeline above. Preserve every existing field, "
            "column, and function exactly as-is unless the new task explicitly "
            "asks to change it — only ADD what the new task actually requires. "
            "Do NOT invent an unrelated pipeline that drops existing "
            "fields/columns/logic.\n\n"
        )
    if existing_schema:
        schema_lines = "\n".join(f"- {col} ({dtype})" for col, dtype in existing_schema)
        context_prefix += (
            "# LIVE cleansed_staging_data TABLE (authoritative — this has real "
            "production rows):\n"
            f"{schema_lines}\n\n"
            "`transform_batch` MUST continue to output a value for every field "
            "listed above (same field names), in addition to whatever new "
            "fields the Jira task below requires. Do not rename or drop any "
            "of these fields.\n\n"
        )

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
def validate_etl_code(code_str: str, sample_payloads: list[dict] = None) -> tuple[bool, str, str]:
    """Validates syntax, required entrypoints, AND that `transform_batch`
    actually runs against real sample data without raising. A dry `exec()`
    alone only proves the function can be *defined* — it doesn't catch a
    generated function that raises (e.g. on a field-name mismatch) the
    moment it's actually called with the real records."""
    # AST Syntax Verification
    try:
        ast.parse(code_str)
    except SyntaxError as se:
        return False, "SyntaxError", f"Line {se.lineno}: {se.msg}"

    # Required Callables Check. Generated code is prompted to reference
    # `__file__` (e.g. `Path(__file__).resolve().parent`) as if it were the
    # persisted etl_pipeline.py module, so provide it here too or every
    # correctly-prompted script fails validation with a bogus NameError.
    local_scope = {"__file__": str(PROJECT_ROOT / "etl_pipeline.py")}
    try:
        exec(code_str, local_scope, local_scope)
    except Exception as e:
        return False, "Runtime Execution Error", f"{traceback.format_exc()}\nDetail: {e}"

    if "transform_batch" not in local_scope or not callable(local_scope["transform_batch"]):
        return False, "Missing Entrypoint", "Missing required function `transform_batch(raw_records)`"

    # Actually call it against the same records it will be executed on for
    # real, so a data-shape mismatch fails validation instead of crashing
    # the agent later during the unguarded execution step.
    try:
        local_scope["transform_batch"](sample_payloads or DEFAULT_SEED_PAYLOADS)
    except Exception as e:
        return (
            False,
            "Transform Execution Error",
            f"{traceback.format_exc()}\nDetail: transform_batch() raised when called "
            f"against the actual input records: {e}",
        )

    return True, "NONE", ""


def _duckdb_type_for(series: pd.Series) -> str:
    # Booleans are a pandas numeric subtype (`is_numeric_dtype` returns True
    # for them), so this check must come BEFORE the numeric check or every
    # boolean field gets miscategorized as DOUBLE instead of BOOLEAN.
    if pd.api.types.is_bool_dtype(series):
        return "BOOLEAN"
    if pd.api.types.is_numeric_dtype(series):
        return "DOUBLE"
    return "VARCHAR"


def insert_cleansed_records(
    cleansed_records: list[dict],
    db_filename: str = "staging.duckdb",
    allow_schema_changes: bool = True,
) -> dict:
    """Inserts already-cleansed records into DuckDB's `cleansed_staging_data`.

    `allow_schema_changes` controls whether this call may CREATE the table or
    ALTER it to add new columns:
    - True (default): used by the explicit "Run Agent 03" flow — schema
      changes are an intentional, reviewable action the user just triggered.
    - False: used by the live ingestion path — schema must stay exactly as
      Agent 03 last left it. A record with fields the table doesn't have
      yet gets those fields silently dropped (not altered in), and if the
      table doesn't exist at all, insertion fails with a clear message
      rather than bootstrapping one implicitly. The raw payload is still
      preserved untouched in `ui_raw_ingestion` either way, so nothing is
      lost — it just won't appear in the cleansed table until Agent 03 is
      (re)run to pick up the new field.
    """
    if not cleansed_records:
        return {"status": "SUCCESS", "processed_count": 0, "sample_output": {}, "new_columns": []}

    db_path = Path(db_filename)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_filename

    conn = duckdb.connect(str(db_path))
    try:
        df_new = pd.DataFrame(cleansed_records)
        new_columns: list[str] = []
        dropped_columns: list[str] = []

        tables = [t[0] for t in conn.execute("SHOW TABLES").fetchall()]
        table_exists = "cleansed_staging_data" in tables

        if not table_exists and not allow_schema_changes:
            return {
                "status": "FAILED",
                "error": (
                    "cleansed_staging_data doesn't exist yet. Run Agent 03 "
                    "once to initialize the schema before live ingestion."
                ),
            }

        if not table_exists:
            conn.register("temp_df", df_new)
            conn.execute("CREATE TABLE cleansed_staging_data AS SELECT * FROM temp_df")
            new_columns = list(df_new.columns)
        else:
            existing_cols = [c[0] for c in conn.execute("DESCRIBE cleansed_staging_data").fetchall()]

            if allow_schema_changes:
                for col in df_new.columns:
                    if col not in existing_cols:
                        col_type = _duckdb_type_for(df_new[col])
                        conn.execute(f"ALTER TABLE cleansed_staging_data ADD COLUMN {col} {col_type}")
                        new_columns.append(col)
            else:
                dropped_columns = [c for c in df_new.columns if c not in existing_cols]
                if dropped_columns:
                    df_new = df_new.drop(columns=dropped_columns)

            if df_new.empty or len(df_new.columns) == 0:
                return {
                    "status": "FAILED",
                    "error": "None of the submitted fields match the existing schema.",
                    "dropped_columns": dropped_columns,
                }

            # Insert by explicit column name (not positional SELECT *): incoming
            # records may have a different/narrower set of fields than earlier
            # ones, so column counts between df_new and the table can differ.
            conn.register("temp_df", df_new)
            col_list = ", ".join(f'"{c}"' for c in df_new.columns)
            conn.execute(
                f"INSERT INTO cleansed_staging_data ({col_list}) SELECT {col_list} FROM temp_df"
            )
    finally:
        # Always release the connection/file lock, even if a statement above
        # raised — otherwise a single bad record permanently wedges the
        # DuckDB file (single-writer) for every request after it, since
        # nothing else could ever open it again without a process restart.
        conn.close()

    return {
        "status": "SUCCESS",
        "processed_count": len(cleansed_records),
        "sample_output": df_new.iloc[0].to_dict() if not df_new.empty else cleansed_records[0],
        "new_columns": new_columns,
        "dropped_columns": dropped_columns,
    }


def sync_cleansed_schema(sample_records: list[dict], db_filename: str = "staging.duckdb") -> dict:
    """CREATE/ALTER `cleansed_staging_data`'s schema to match `sample_records`'
    shape, without inserting any rows. This is Workflow 1's DDL step — it
    mirrors Agent 04's DDL-only behavior for `customer_master`, so a new
    field's column exists as soon as Agent 03 generates code for it, before
    any real customer data arrives via Workflow 2's live ingestion (which
    runs with allow_schema_changes=False and would otherwise silently drop
    that field)."""
    if not sample_records:
        return {"new_columns": []}

    db_path = Path(db_filename)
    if not db_path.is_absolute():
        db_path = PROJECT_ROOT / db_filename

    conn = duckdb.connect(str(db_path))
    try:
        df_sample = pd.DataFrame(sample_records)
        new_columns: list[str] = []
        tables = [t[0] for t in conn.execute("SHOW TABLES").fetchall()]
        table_exists = "cleansed_staging_data" in tables

        if not table_exists:
            conn.register("temp_df", df_sample)
            conn.execute("CREATE TABLE cleansed_staging_data AS SELECT * FROM temp_df WHERE 1=0")
            new_columns = list(df_sample.columns)
        else:
            existing_cols = [c[0] for c in conn.execute("DESCRIBE cleansed_staging_data").fetchall()]
            for col in df_sample.columns:
                if col not in existing_cols:
                    col_type = _duckdb_type_for(df_sample[col])
                    conn.execute(f"ALTER TABLE cleansed_staging_data ADD COLUMN {col} {col_type}")
                    new_columns.append(col)
    finally:
        conn.close()

    return {"new_columns": new_columns}


def run_etl_in_duckdb(
    etl_code: str,
    raw_payloads: list[dict],
    schema_sample_payloads: list[dict],
    db_filename: str = "staging.duckdb",
) -> dict:
    """Persists a generated `transform_batch` script, always syncs the table's
    schema against `schema_sample_payloads` (Workflow 1's DDL step — this
    runs even with zero real records), and, only if `raw_payloads` are real
    records (not just a validation sample), inserts the transformed results.
    Called with an empty `raw_payloads` list when there's no real data yet,
    so re-running Agent 03 with no new real data doesn't duplicate rows on
    every click, while still keeping the schema current."""
    etl_script_path = PROJECT_ROOT / "etl_pipeline.py"

    # Persist code to project root for streamlit_app.py imports
    with open(etl_script_path, "w", encoding="utf-8") as f:
        f.write(etl_code)

    local_scope = {"__file__": str(etl_script_path)}
    exec(etl_code, local_scope, local_scope)
    transform_fn = local_scope["transform_batch"]

    schema_result = sync_cleansed_schema(transform_fn(schema_sample_payloads), db_filename=db_filename)

    if not raw_payloads:
        return {
            "status": "SUCCESS",
            "processed_count": 0,
            "sample_output": {},
            "new_columns": schema_result["new_columns"],
        }

    cleansed_records = transform_fn(raw_payloads)
    return insert_cleansed_records(cleansed_records, db_filename=db_filename)
# endregion


# region 3b. DETERMINISTIC LIVE INGESTION PATH (no LLM call required per-request)
# ============================================================================
# Used by api_bridge.py's /api/ingest route: cleanses a single record submitted
# by the UI and stores it into DuckDB, without paying for/depending on an LLM
# call on every live HTTP request.
# ============================================================================
def default_transform_batch(raw_records: list[dict]) -> list[dict]:
    """Deterministic fallback cleansing: strips strings, masks Aadhaar numbers,
    and computes a simple risk_index from credit_score/annual_income."""
    cleansed_records = []
    for record in raw_records:
        if not isinstance(record, dict):
            continue
        cleansed = {}
        for key, value in record.items():
            cleansed[key] = value.strip() if isinstance(value, str) else value

        aadhaar = cleansed.get("aadhaar_no")
        if isinstance(aadhaar, str) and aadhaar:
            digits = "".join(ch for ch in aadhaar if ch.isdigit())
            cleansed["aadhaar_no"] = ("X" * max(0, len(digits) - 4)) + digits[-4:]

        credit_score = cleansed.get("credit_score")
        annual_income = cleansed.get("annual_income")
        try:
            score = float(credit_score) if credit_score is not None else 650.0
            income = float(annual_income) if annual_income is not None else 500000.0
            risk_index = round(max(0.0, min(100.0, (850 - score) / 5.5 - (income / 100000))), 2)
        except (TypeError, ValueError):
            risk_index = 50.0
        cleansed["risk_index"] = risk_index

        cleansed_records.append(cleansed)
    return cleansed_records


def process_ingested_payload(record: dict, db_filename: str = "staging.duckdb") -> dict:
    """Agent 03 live entrypoint: cleanses one UI-submitted record (already
    mapped to canonical field names) and persists it into DuckDB's
    cleansed_staging_data. Schema changes are NOT made here — only Agent 03
    (via the "Run Agent 03" button) is allowed to create/alter this table.
    A field the table doesn't have yet is silently dropped from the
    cleansed row (see `dropped_columns` in the result); the full raw
    payload is still preserved as-is in `ui_raw_ingestion` regardless."""
    cleansed_records = default_transform_batch([record])
    return insert_cleansed_records(cleansed_records, db_filename=db_filename, allow_schema_changes=False)
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

    # Real payloads to actually write to DuckDB — empty when this run has no
    # new real data, so a re-run doesn't re-insert stale records.
    real_payloads = raw_payloads or getattr(state, "raw_payloads", None) or []
    # Validation always exercises transform_batch against a concrete sample so
    # self-healing catches data-shape bugs even when there's no real data yet
    # (e.g. the very first run, before any UI submission has occurred).
    validation_payloads = real_payloads or DEFAULT_SEED_PAYLOADS

    # Self-Healing Retry Loop
    max_retries = 3
    etl_code = ""
    healing_context = None
    # Carry the previously-generated pipeline forward as a baseline to
    # extend, so re-running Agent 03 for a new Jira story doesn't throw away
    # everything generated for earlier stories.
    baseline_code = getattr(state, "etl_code", None) or None
    # Same live-schema introspection Agent 04 uses — the actual DuckDB table
    # is authoritative regardless of what's (or isn't) cached in session state.
    existing_schema = fetch_existing_duckdb_schema()
    logger.info(
        f"Live cleansed_staging_data schema: "
        f"{'extending ' + str(len(existing_schema)) + ' existing columns' if existing_schema else 'table does not exist yet'}"
    )

    err_type, err_traceback = "LLM Generation Error", ""
    for attempt in range(1, max_retries + 1):
        logger.info(f"Generating ETL Pipeline (Attempt {attempt}/{max_retries})...")
        try:
            etl_code = generate_etl_pipeline(
                jira_spec,
                existing_code=healing_context,
                baseline_code=baseline_code,
                existing_schema=existing_schema,
            )
        except Exception as e:
            # A flaky/slow LLM call (timeout, rate limit, malformed response)
            # should count as a failed healing attempt, not crash the agent.
            logger.warning(f"⚠️ [ETL GENERATION ERROR] Attempt {attempt}/{max_retries}: {e}")
            healing_context = f"# ERROR CATEGORY: LLM Generation Error\n# DETAIL:\n{e}\n"
            is_valid = False
            err_type, err_traceback = "LLM Generation Error", str(e)
            continue

        is_valid, err_type, err_traceback = validate_etl_code(etl_code, sample_payloads=validation_payloads)
        if is_valid:
            logger.info(f"✅ [SELF-HEALING SUCCESS] Valid ETL pipeline code generated on attempt #{attempt}!")
            break

        logger.warning(f"⚠️ [ETL VALIDATION ERROR]: {err_type}\n{err_traceback}")
        healing_context = f"# ERROR CATEGORY: {err_type}\n# TRACEBACK:\n{err_traceback}\n"
        is_valid = False

    if not is_valid:
        # All self-healing attempts failed; don't execute known-broken code.
        # Fall back to the deterministic transform so the pipeline still runs.
        error_msg = (
            f"Agent 03: LLM failed to generate valid ETL code after {max_retries} attempts "
            f"({err_type}). Falling back to the deterministic default transform."
        )
        logger.error(error_msg)
        state.errors.append(error_msg)
        state.etl_code = etl_code
        if real_payloads:
            result = insert_cleansed_records(default_transform_batch(real_payloads))
        else:
            result = {"status": "SUCCESS", "processed_count": 0, "sample_output": {}, "new_columns": []}
    else:
        state.etl_code = etl_code
        logger.info(f"Executing ETL runner against DuckDB with {len(real_payloads)} real record(s)...")
        try:
            result = run_etl_in_duckdb(state.etl_code, real_payloads, validation_payloads)
        except Exception as e:
            # Validation passed against these same payloads moments ago, so
            # this should be rare, but never let an execution-time surprise
            # crash the whole agent/dashboard — degrade gracefully instead.
            error_msg = f"Agent 03: validated ETL code raised at execution time ({e}); falling back to default transform."
            logger.error(error_msg)
            state.errors.append(error_msg)
            if real_payloads:
                result = insert_cleansed_records(default_transform_batch(real_payloads))
            else:
                result = {"status": "SUCCESS", "processed_count": 0, "sample_output": {}, "new_columns": []}

    if result.get("sample_output"):
        state.sample_cleansed_output = result["sample_output"]

    logger.info(f"✅ Agent 03 completed successfully. Processed {result['processed_count']} records.")
    return state
# endregion