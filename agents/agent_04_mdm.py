import os
from pathlib import Path
import re
import subprocess
import time
import json
from typing import Any, Callable, Dict, List, Optional, Tuple

from dotenv import load_dotenv
import duckdb
import pandas as pd
import psycopg2
from psycopg2 import sql
from pydantic import BaseModel, Field
import requests
from requests.auth import HTTPBasicAuth

from core.llm_factory import get_llm
from core.state import ProjectState

load_dotenv()


# ==========================================
# Step 1: Jira Specification Reader
# ==========================================

def fetch_mdm_jira_issue(issue_key: str, logger: Callable[[str, str], None] = None) -> str:
    """Fetches MDM specification dynamically from Jira REST API."""
    def log(msg: str, level: str = "INFO"):
        if logger:
            logger(msg, level)
        else:
            print(msg)

    if not issue_key:
        return ""

    atlassian_url = os.getenv("ATLASSIAN_URL", "https://shashankwv.atlassian.net")
    url = f"{atlassian_url}/rest/api/3/issue/{issue_key}"
    
    auth = HTTPBasicAuth(
        os.getenv("ATLASSIAN_EMAIL", ""),
        os.getenv("ATLASSIAN_API_TOKEN", "")
    )
    headers = {"Accept": "application/json"}

    try:
        response = requests.get(url, auth=auth, headers=headers, timeout=10)
        if response.status_code != 200:
            log(f"Warning: Could not fetch Jira issue {issue_key}. Status: {response.status_code}", "WARN")
            return ""

        data = response.json()
        summary = data["fields"].get("summary", "")
        
        description_text = ""
        desc_field = data["fields"].get("description")
        if desc_field and "content" in desc_field:
            for block in desc_field["content"]:
                for item in block.get("content", []):
                    if item.get("type") == "text":
                        description_text += item.get("text", "") + "\n"

        return f"Summary: {summary}\nDescription:\n{description_text.strip()}"
    except Exception as e:
        log(f"Failed to fetch Jira MDM issue: {e}", "WARN")
        return ""


# ==========================================
# Step 2: Self-Healing Postgres Connection Manager
# ==========================================

def get_postgres_connection(db_uri: Optional[str] = None):
    """Establishes and returns an active connection to PostgreSQL MDM Database."""
    connection_string = db_uri or os.getenv(
        "POSTGRES_CONNECTION_URI",
        "postgresql://postgres:postgres@localhost:5432/mdm_db",
    )
    return psycopg2.connect(connection_string)


def ensure_postgres_running(container_name: str = "mdm-postgres", logger: Callable[[str, str], None] = None) -> bool:
    """Self-healing connection manager: verifies connectivity and auto-starts PostgreSQL if offline."""
    def log(msg: str, level: str = "INFO"):
        if logger:
            logger(msg, level)
        else:
            print(msg)

    db_uri = os.getenv("POSTGRES_CONNECTION_URI", "postgresql://postgres:postgres@localhost:5432/mdm_db")
    try:
        conn = psycopg2.connect(db_uri, connect_timeout=3)
        conn.close()
        return True
    except Exception:
        pass

    try:
        log(f"⚠️ [Self-Healing Engine] PostgreSQL offline. Recovering container '{container_name}'...", "WARN")
        check_cmd = f"docker inspect -f '{{{{.State.Running}}}}' {container_name}"
        result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)

        if result.stdout.strip() == "true":
            return True

        exists_cmd = f"docker ps -a --format '{{{{.Names}}}}' | grep -w {container_name}"
        exists_result = subprocess.run(exists_cmd, shell=True, capture_output=True, text=True)

        if container_name in exists_result.stdout:
            subprocess.run(f"docker start {container_name}", shell=True, check=True, capture_output=True)
        else:
            run_cmd = (
                f"docker run --name {container_name} -e POSTGRES_DB=mdm_db -e "
                "POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432 "
                "-d postgres:latest"
            )
            subprocess.run(run_cmd, shell=True, check=True, capture_output=True)

        for _ in range(10):
            time.sleep(1)
            try:
                conn = psycopg2.connect(db_uri)
                conn.close()
                log("✅ [Self-Healing Engine] PostgreSQL database operational!", "SUCCESS")
                return True
            except psycopg2.OperationalError:
                continue

        return False
    except Exception as e:
        log(f"❌ [Self-Healing Engine] Failed to repair PostgreSQL instance: {e}", "WARN")
        return False


# ==========================================
# Step 3: Dynamic LLM Mapping & Agentic Schema Architect
# ==========================================

class RecordMappingSchema(BaseModel):
    primary_key: str = Field(
        description="The field name in the raw payload that serves as the natural primary identifier key (e.g., id, customer_id, uuid)."
    )
    column_mapping: Dict[str, str] = Field(
        description="Dictionary mapping each raw payload key to the target PostgreSQL column name dynamically."
    )
    essential_fields: List[str] = Field(
        description="List of target PostgreSQL column names that are mandatory/essential (cannot be NULL)."
    )


class MDMDDLResponse(BaseModel):
    ddl_sql: str = Field(
        description="Executable PostgreSQL DDL SQL script containing CREATE TABLE or ALTER TABLE ADD/DROP statements."
    )


def resolve_payload_mapping_via_llm(
    jira_spec: str, 
    sample_payload: Dict[str, Any], 
    existing_columns: List[str],
    logger: Callable[[str, str], None] = None
) -> RecordMappingSchema:
    """Dynamically maps raw incoming payload keys to target database columns aligned with Jira."""
    def log(msg: str, level: str = "INFO"):
        if logger:
            logger(msg, level)
        else:
            print(msg)

    try:
        structured_llm = get_llm(schema=RecordMappingSchema)
        prompt = f"""You are an autonomous Master Data Management (MDM) Integration Agent.

Jira Requirements & Specification:
{jira_spec}

Incoming Raw Payload Keys:
{list(sample_payload.keys())}

Existing PostgreSQL Columns:
{existing_columns}

TASK:
1. Identify the unique primary identifier field from the incoming raw payload keys (prefer 'id' or explicit system primary identifiers if present).
2. Create a dictionary mapping raw payload keys to existing PostgreSQL columns where equivalent, or map to clean database column names for new fields.
3. Identify strictly mandatory/essential target column names that cannot be NULL based on Jira requirements or domain context. Only include primary keys or explicit business criticality fields.
"""
        mapping_res: RecordMappingSchema = structured_llm.invoke(prompt)
        log(f"🧠 [Agentic Resolver]: Primary Key -> '{mapping_res.primary_key}' | Essential Columns -> {mapping_res.essential_fields}", "INFO")
        return mapping_res
    except Exception as e:
        log(f"Warning: LLM Payload Resolver failed: {e}. Falling back to dynamic key detection.", "WARN")
        raw_keys = list(sample_payload.keys())
        pk = "id" if "id" in raw_keys else (raw_keys[0] if raw_keys else "id")
        return RecordMappingSchema(
            primary_key=pk,
            column_mapping={k: k for k in raw_keys},
            essential_fields=[pk]
        )


def fetch_existing_customer_master_schema(table_name: str = "customer_master", db_uri: Optional[str] = None) -> List[Tuple[str, str]]:
    """Queries PostgreSQL information_schema to inspect existing table columns and data types."""
    try:
        conn = get_postgres_connection(db_uri)
        cur = conn.cursor()
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = %s "
            "ORDER BY ordinal_position",
            (table_name,)
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception:
        return []


def generate_production_ddl(
    jira_spec: str, 
    sample_record: Optional[dict] = None, 
    existing_schema: List[Tuple[str, str]] = None,
    table_name: str = "customer_master",
    logger: Callable[[str, str], None] = None
) -> str:
    """Generates dynamic PostgreSQL DDL via LLM."""
    def log(msg: str, level: str = "INFO"):
        if logger:
            logger(msg, level)
        else:
            print(msg)

    structured_llm = get_llm(schema=MDMDDLResponse)

    if existing_schema:
        schema_lines = "\n".join(f"- {col} ({dtype})" for col, dtype in existing_schema)
        schema_instruction = f"""
TABLE STATUS: Table `public.{table_name}` ALREADY EXISTS in PostgreSQL with these current columns:
{schema_lines}

TASK:
1. Inspect incoming payload fields. Generate `ALTER TABLE public.{table_name} ADD COLUMN IF NOT EXISTS <column_name> VARCHAR;` for missing columns.
2. DO NOT add restrictive CHECK constraints or NOT NULL constraints on non-essential payload fields.
"""
    else:
        schema_instruction = f"""
TABLE STATUS: Table `public.{table_name}` DOES NOT EXIST in PostgreSQL yet.

TASK: Generate a complete `CREATE TABLE IF NOT EXISTS public.{table_name}` statement.
Use standard baseline audit columns (`id VARCHAR PRIMARY KEY`, `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`, `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`).
All other incoming domain columns should default to flexible types (VARCHAR, INT, DOUBLE PRECISION, TIMESTAMP) WITHOUT restrictive CHECK or NOT NULL constraints.
"""

    sample_fields_str = f"Sample Payload Fields: {list(sample_record.keys())}" if sample_record else "No active sample payload."

    prompt = f"""You are an autonomous Master Data Management (MDM) Database Architect Agent.

Jira Specification:
{jira_spec}

{sample_fields_str}

{schema_instruction}

STRICT AGENTIC CONSTRAINTS:
1. Avoid restrictive CHECK or NOT NULL constraints on non-essential domain fields.
2. Do NOT write transaction blocks like `BEGIN;` or `COMMIT;`.
3. Return executable raw SQL statements only.
"""

    try:
        response: MDMDDLResponse = structured_llm.invoke(prompt)
        raw_ddl = response.ddl_sql.strip()
        raw_ddl = re.sub(r"(?i)^\s*BEGIN\s*;\s*", "", raw_ddl)
        raw_ddl = re.sub(r"(?i)^\s*COMMIT\s*;\s*", "", raw_ddl)
        return raw_ddl.strip()
    except Exception as e:
        log(f"LLM DDL Generation Note: {e}. Falling back to default execution.", "WARN")
        return ""


def execute_mdm_on_postgres(
    ddl_sql: str, 
    db_uri: Optional[str] = None, 
    auto_heal: bool = True,
    logger: Callable[[str, str], None] = None
) -> dict:
    """Executes dynamic DDL scripts directly against PostgreSQL."""
    def log(msg: str, level: str = "INFO"):
        if logger:
            logger(msg, level)
        else:
            print(msg)

    if not ddl_sql or ddl_sql.strip().startswith("--"):
        return {"status": "SUCCESS", "message": "No DDL execution required."}

    for attempt in range(2):
        try:
            conn = get_postgres_connection(db_uri)
            conn.autocommit = True
            cursor = conn.cursor()
            cursor.execute(ddl_sql)
            cursor.close()
            conn.close()

            return {
                "status": "SUCCESS",
                "message": "DDL executed successfully on PostgreSQL database.",
            }

        except psycopg2.OperationalError as e:
            if auto_heal and attempt == 0:
                log("🔧 [Self-Healing Engine] Recovering PostgreSQL connection...", "WARN")
                if ensure_postgres_running(logger=logger):
                    continue

            return {"status": "FAILED", "error": str(e), "message": "PostgreSQL connection failure."}
        except Exception as e:
            return {"status": "FAILED", "error": str(e), "message": f"DDL execution error: {str(e)}"}


# ==========================================
# Step 4: Dynamic Agentic Sync & Self-Healing Upsert Engine
# ==========================================

def clean_payload_value(val: Any) -> Any:
    """Agentic Value Normalizer: converts NaN, 'nan', 'null', and empty strings to Python None (SQL NULL)."""
    if val is None or pd.isna(val):
        return None
    if isinstance(val, str):
        cleaned_str = val.strip()
        if cleaned_str.lower() in ["nan", "none", "null", ""]:
            return None
        return cleaned_str
    return val


def sync_staging_to_mdm(
    table_name: str = "customer_master", 
    jira_spec: str = "",
    db_uri: Optional[str] = None,
    logger: Callable[[str, str], None] = None
) -> dict:
    """
    Pure Agentic Sync Engine with Self-Healing Constraint Resolution:
    - Resolves raw key mapping and primary key dynamically.
    - Dynamically alters table schema to add missing columns.
    - Dynamically resolves NOT NULL constraint failures on ingestion automatically.
    """
    def log(msg: str, level: str = "INFO"):
        if logger:
            logger(msg, level)
        else:
            print(msg)

    duckdb_path = Path("etl/etl.duckdb")
    if not duckdb_path.exists():
        return {"status": "SKIPPED", "message": "No DuckDB database file found."}

    try:
        conn = duckdb.connect(str(duckdb_path), read_only=True)
        tables = [row[0] for row in conn.execute("SHOW TABLES").fetchall()]
        
        target_table = None
        if "staging_ui" in tables:
            target_table = "staging_ui"
        elif "landing_ui" in tables:
            target_table = "landing_ui"

        if not target_table:
            conn.close()
            return {"status": "SKIPPED", "message": "No staging table found in DuckDB."}

        df = conn.execute(f"SELECT * FROM {target_table}").fetchdf()
        conn.close()

        if df.empty:
            return {"status": "SKIPPED", "message": f"No records in {target_table} to migrate."}

        # Step 1: Extract and clean raw payload dictionaries
        records_to_upsert = []
        for _, row in df.iterrows():
            record_data = {}
            if "record" in row and row["record"]:
                rec_val = row["record"]
                record_data = json.loads(rec_val) if isinstance(rec_val, str) else rec_val
            elif "payload" in row and row["payload"]:
                p_val = row["payload"]
                record_data = json.loads(p_val) if isinstance(p_val, str) else p_val

            for col in df.columns:
                if col not in ["record", "payload", "staged_at", "ingested_at"] and row[col] is not None:
                    record_data[col] = row[col]

            cleaned_record = {k: clean_payload_value(v) for k, v in record_data.items()}
            if cleaned_record:
                records_to_upsert.append(cleaned_record)

        if not records_to_upsert:
            return {"status": "SKIPPED", "message": "No valid payloads extracted."}

        pg_conn = get_postgres_connection(db_uri)
        pg_conn.autocommit = True
        cur = pg_conn.cursor()

        # Step 2: Retrieve current Postgres table schema
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s",
            (table_name,),
        )
        existing_cols = {row[0] for row in cur.fetchall()}

        # Step 3: Pure Agentic Payload Resolver via LLM
        mapping_info = resolve_payload_mapping_via_llm(jira_spec, records_to_upsert[0], list(existing_cols), logger=logger)
        raw_pk_key = mapping_info.primary_key
        key_map = mapping_info.column_mapping

        # Target PK column name in Postgres
        pk_field = key_map.get(raw_pk_key, raw_pk_key)

        # Ensure PK column exists in DB
        if pk_field not in existing_cols and pk_field not in ["created_at", "updated_at"]:
            log(f"✨ [Schema Migration]: Adding primary key column '{pk_field}' to `public.{table_name}`...", "INFO")
            cur.execute(sql.SQL("ALTER TABLE public.{} ADD COLUMN IF NOT EXISTS {} VARCHAR;").format(
                sql.Identifier(table_name), sql.Identifier(pk_field)
            ))
            existing_cols.add(pk_field)

        success_count = 0
        failed_records = []

        # Step 4: Dynamic Alignment, Auto-Schema Expansion & Upsert Loop
        for rec in records_to_upsert:
            # Remap keys dynamically using LLM mapping
            mapped_rec = {key_map.get(k, k): v for k, v in rec.items()}

            # Primary Key validation
            if not mapped_rec.get(pk_field):
                error_desc = f"Validation Error: Essential primary key field '{pk_field}' is missing or NULL."
                log(f"❌ [Record Rejected]: {error_desc}", "WARN")
                failed_records.append({"record": rec, "error": error_desc})
                continue

            # Dynamically expand table columns for any new payload fields
            for col in mapped_rec.keys():
                if col not in existing_cols and col not in ["created_at", "updated_at"]:
                    log(f"✨ [Agentic Schema Expansion]: Dynamically adding new column '{col}' to PostgreSQL table 'public.{table_name}'", "INFO")
                    try:
                        cur.execute(sql.SQL("ALTER TABLE public.{} ADD COLUMN IF NOT EXISTS {} VARCHAR;").format(
                            sql.Identifier(table_name), sql.Identifier(col)
                        ))
                        existing_cols.add(col)
                    except Exception as col_err:
                        log(f"⚠️ Could not add column '{col}': {col_err}", "WARN")

            formatted_rec = {
                k: (json.dumps(v) if isinstance(v, (dict, list)) else v)
                for k, v in mapped_rec.items() if k in existing_cols
            }

            cols = list(formatted_rec.keys())
            update_cols = [c for c in cols if c != pk_field]

            if update_cols:
                upsert_query = sql.SQL(
                    "INSERT INTO public.{table} ({cols}) VALUES ({vals}) "
                    "ON CONFLICT ({pk}) DO UPDATE SET {updates}, updated_at = CURRENT_TIMESTAMP"
                ).format(
                    table=sql.Identifier(table_name),
                    cols=sql.SQL(", ").join(sql.Identifier(c) for c in cols),
                    vals=sql.SQL(", ").join(sql.Placeholder() for _ in cols),
                    pk=sql.Identifier(pk_field),
                    updates=sql.SQL(", ").join(
                        sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in update_cols
                    ),
                )
            else:
                upsert_query = sql.SQL(
                    "INSERT INTO public.{table} ({cols}) VALUES ({vals}) ON CONFLICT ({pk}) DO NOTHING"
                ).format(
                    table=sql.Identifier(table_name),
                    cols=sql.SQL(", ").join(sql.Identifier(c) for c in cols),
                    vals=sql.SQL(", ").join(sql.Placeholder() for _ in cols),
                    pk=sql.Identifier(pk_field),
                )

            # Self-Healing Retry Loop for Database Execution
            try:
                cur.execute(upsert_query, [formatted_rec[c] for c in cols])
                success_count += 1
            except psycopg2.Error as db_err:
                err_msg = str(db_err)
                log(f"⚠️ [Sync Warning]: Database error on record ({mapped_rec.get(pk_field)}): {err_msg}", "WARN")

                # Self-Healing 1: Handle NOT NULL constraint error dynamically by removing restriction
                if "violates not-null constraint" in err_msg.lower():
                    col_match = re.search(r'column "([^"]+)"', err_msg)
                    if col_match:
                        null_col = col_match.group(1)
                        log(f"🔧 [Self-Healing Engine] Removing restrictive NOT NULL constraint from column '{null_col}'...", "WARN")
                        try:
                            cur.execute(sql.SQL("ALTER TABLE public.{} ALTER COLUMN {} DROP NOT NULL;").format(
                                sql.Identifier(table_name), sql.Identifier(null_col)
                            ))
                            # Retry record insertion
                            cur.execute(upsert_query, [formatted_rec[c] for c in cols])
                            success_count += 1
                            continue
                        except Exception as retry_e:
                            err_msg = str(retry_e)

                # Self-Healing 2: Handle missing ON CONFLICT constraint error dynamically
                if "no unique or exclusion constraint" in err_msg.lower():
                    try:
                        log(f"🔧 [Self-Healing Engine] Adding missing unique index for ON CONFLICT ({pk_field})...", "WARN")
                        cur.execute(sql.SQL("CREATE UNIQUE INDEX IF NOT EXISTS {} ON public.{} ({});").format(
                            sql.Identifier(f"idx_unique_{table_name}_{pk_field.lower()}"),
                            sql.Identifier(table_name),
                            sql.Identifier(pk_field)
                        ))
                        # Retry record insertion
                        cur.execute(upsert_query, [formatted_rec[c] for c in cols])
                        success_count += 1
                        continue
                    except Exception as retry_e:
                        err_msg = str(retry_e)

                # Self-Healing 3: Drop blocking check constraint automatically if triggered
                if "violates check constraint" in err_msg.lower():
                    constraint_match = re.search(r'constraint "([^"]+)"', err_msg)
                    if constraint_match:
                        blocking_constraint = constraint_match.group(1)
                        log(f"🔧 [Self-Healing Engine] Dropping blocking constraint '{blocking_constraint}'...", "WARN")
                        cur.execute(sql.SQL("ALTER TABLE public.{} DROP CONSTRAINT IF EXISTS {};").format(
                            sql.Identifier(table_name),
                            sql.Identifier(blocking_constraint)
                        ))
                        # Retry execution
                        cur.execute(upsert_query, [formatted_rec[c] for c in cols])
                        success_count += 1
                        continue

                failed_records.append({"record": rec, "error": err_msg})

        cur.close()
        pg_conn.close()

        status_flag = "SUCCESS" if success_count > 0 else ("FAILED" if failed_records else "SKIPPED")
        msg = f"MDM Migration Complete: {success_count} record(s) upserted into PostgreSQL `public.{table_name}`."
        if failed_records:
            msg += f" {len(failed_records)} record(s) failed field validation constraints."

        return {
            "status": status_flag,
            "message": msg,
            "count": success_count,
            "failed": failed_records
        }

    except Exception as e:
        return {"status": "FAILED", "error": str(e)}


# ==========================================
# Step 5: Pure PostgreSQL Reader Guardrail
# ==========================================

def fetch_postgres_mdm_data(
    table_name: str = "customer_master", 
    db_uri: Optional[str] = None,
    logger: Callable[[str, str], None] = None
) -> List[Dict[str, Any]]:
    """Reads master records directly from PostgreSQL."""
    def log(msg: str, level: str = "INFO"):
        if logger:
            logger(msg, level)
        else:
            print(msg)

    try:
        ensure_postgres_running(logger=logger)
        conn = get_postgres_connection(db_uri)
        cur = conn.cursor()
        
        cur.execute(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = %s);",
            (table_name,)
        )
        if not cur.fetchone()[0]:
            cur.close()
            conn.close()
            return []

        cur.execute(sql.SQL("SELECT * FROM public.{} ORDER BY created_at DESC;").format(sql.Identifier(table_name)))
        col_names = [desc[0] for desc in cur.description]
        rows = cur.fetchall()
        cur.close()
        conn.close()

        return [dict(zip(col_names, row)) for row in rows]
    except Exception as e:
        log(f"Error reading PostgreSQL MDM table: {e}", "WARN")
        return []


# ==========================================
# Step 6: Autonomous Agent Orchestrator
# ==========================================

def run_mdm_agent_autonomous(
    state: ProjectState, 
    sample_record: Optional[dict] = None, 
    table_name: str = "customer_master",
    execute_live: bool = True,
    reset: bool = False,
    logger: Callable[[str, str], None] = None
) -> ProjectState:
    """Autonomous Agent 04 Controller."""
    def log(msg: str, level: str = "INFO"):
        if logger:
            logger(msg, level)
        else:
            print(msg)

    log("--- Running Autonomous Agent 04 (PostgreSQL MDM Engine) ---", "EXEC")

    if reset:
        state.mdm_ddl = ""
        if execute_live:
            try:
                ensure_postgres_running(logger=logger)
                pg_conn = get_postgres_connection()
                pg_conn.autocommit = True
                cur = pg_conn.cursor()
                log(f"🗑️ [Start Fresh]: Dropping table public.{table_name}...", "WARN")
                cur.execute(f"DROP TABLE IF EXISTS public.{table_name} CASCADE;")
                cur.close()
                pg_conn.close()
            except Exception as e:
                log(f"⚠️ Failed to drop table during reset: {e}", "WARN")

    jira_issue_key = getattr(state, "jira_mdm_issue_key", None) or getattr(state, "jira_issue_key", None)
    jira_spec = fetch_mdm_jira_issue(jira_issue_key, logger=logger) if jira_issue_key else ""
    if not jira_spec:
        jira_spec = getattr(state, "jira_mdm_task", None) or "Maintain master table schema dynamically in sync with incoming payload."

    sample_payload = sample_record or getattr(state, "sample_cleansed_output", None)
    if not sample_payload:
        try:
            duckdb_path = Path("etl/etl.duckdb")
            if duckdb_path.exists():
                conn = duckdb.connect(str(duckdb_path), read_only=True)
                tables = [row[0] for row in conn.execute("SHOW TABLES").fetchall()]
                if "staging_ui" in tables:
                    df = conn.execute("SELECT * FROM staging_ui LIMIT 1").fetchdf()
                    if not df.empty:
                        row_dict = df.to_dict(orient="records")[0]
                        if "record" in row_dict and row_dict["record"]:
                            rec_val = row_dict["record"]
                            sample_payload = json.loads(rec_val) if isinstance(rec_val, str) else rec_val
                        elif "payload" in row_dict and row_dict["payload"]:
                            payload_val = row_dict["payload"]
                            sample_payload = json.loads(payload_val) if isinstance(payload_val, str) else payload_val
                        else:
                            sample_payload = row_dict
                conn.close()
        except Exception as e:
            log(f"DuckDB Inspection Note: {e}", "INFO")

    try:
        ensure_postgres_running(logger=logger)

        existing_schema = fetch_existing_customer_master_schema(table_name=table_name)
        ddl_sql = generate_production_ddl(jira_spec, sample_payload, existing_schema=existing_schema, table_name=table_name, logger=logger)
        state.mdm_ddl = ddl_sql

        if execute_live and ddl_sql:
            exec_res = execute_mdm_on_postgres(ddl_sql, logger=logger)
            status_level = "SUCCESS" if exec_res["status"] == "SUCCESS" else "WARN"
            log(f"PostgreSQL DDL Execution: {exec_res['status']} | {exec_res.get('message') or exec_res.get('error')}", status_level)

        if execute_live:
            sync_res = sync_staging_to_mdm(table_name=table_name, jira_spec=jira_spec, logger=logger)
            status_level = "SUCCESS" if sync_res["status"] == "SUCCESS" else "WARN"
            log(f"MDM Staging Sync: {sync_res['status']} | {sync_res.get('message') or sync_res.get('error')}", status_level)
            
            if sync_res.get("failed"):
                for failure in sync_res["failed"]:
                    err_text = f"MDM Ingestion Warning: {failure['error']}"
                    if hasattr(state, "errors") and isinstance(state.errors, list):
                        state.errors.append(err_text)

        # Set mdm_records on ProjectState
        records = fetch_postgres_mdm_data(table_name=table_name, logger=logger)
        if hasattr(state, "mdm_records"):
            state.mdm_records = records
        else:
            setattr(state, "mdm_records", records)

    except Exception as e:
        error_msg = f"Autonomous Agent 04 Error: {str(e)}"
        log(error_msg, "WARN")
        if hasattr(state, "errors") and isinstance(state.errors, list):
            state.errors.append(error_msg)

    return state


def ensure_table_initialized(table_name: str = "customer_master", sample_record: Optional[dict] = None) -> bool:
    """Helper method called by orchestrators to guarantee Postgres table exists."""
    try:
        if not ensure_postgres_running():
            return False

        existing_schema = fetch_existing_customer_master_schema(table_name=table_name)
        if not existing_schema:
            jira_spec = "Initialize baseline customer master table."
            ddl_sql = generate_production_ddl(
                jira_spec=jira_spec,
                sample_record=sample_record,
                existing_schema=[],
                table_name=table_name
            )
            if ddl_sql:
                res = execute_mdm_on_postgres(ddl_sql)
                return res.get("status") == "SUCCESS"
        return True
    except Exception as e:
        print(f"Error in ensure_table_initialized: {e}")
        return False


if __name__ == "__main__":
    test_state = ProjectState()
    run_mdm_agent_autonomous(test_state, execute_live=True)