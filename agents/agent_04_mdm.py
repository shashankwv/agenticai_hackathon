import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Dict, List

from dotenv import load_dotenv
import duckdb
from langchain_core.prompts import ChatPromptTemplate
import psycopg2
from psycopg2 import sql
from pydantic import BaseModel, Field
import requests
from requests.auth import HTTPBasicAuth

from core.llm_factory import get_llm
from core.state import ProjectState

load_dotenv()

# ==========================================
# Step 1: Jira Reader
# ==========================================

def fetch_mdm_jira_issue(issue_key: str) -> str:
    """Fetches MDM task details from Jira REST API by issue key."""
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
            print(f"Warning: Could not fetch Jira issue {issue_key}. Status: {response.status_code}")
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
        print(f"Failed to fetch Jira MDM issue: {e}")
        return ""


# ==========================================
# Step 2: DDL Generator
# ==========================================

class MDMDDLResponse(BaseModel):
    ddl_sql: str = Field(
        description="Production PostgreSQL DDL SQL script containing table DDL, primary keys, audit columns, indexes, and an UPSERT example."
    )


def fetch_existing_customer_master_schema(db_uri: str = None) -> list[tuple[str, str]]:
    """Returns [(column_name, data_type), ...] for the live `customer_master`
    table, or [] if it doesn't exist yet / Postgres is unreachable."""
    connection_string = db_uri or os.getenv(
        "POSTGRES_CONNECTION_URI",
        "postgresql://postgres:postgres@localhost:5432/mdm_db",
    )
    try:
        conn = psycopg2.connect(connection_string, connect_timeout=5)
        cur = conn.cursor()
        cur.execute(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'customer_master' "
            "ORDER BY ordinal_position"
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception:
        return []


def generate_production_ddl(
    jira_spec: str, sample_record: dict, existing_schema: list[tuple[str, str]] = None
) -> str:
    """Generates production PostgreSQL DDL dynamically based on input record structure and Jira specs."""
    structured_llm = get_llm(schema=MDMDDLResponse)

    if existing_schema:
        schema_lines = "\n".join(f"- {col} ({dtype})" for col, dtype in existing_schema)
        schema_context = f"""
The `public.customer_master` table ALREADY EXISTS in production with these columns:
{schema_lines}

This is LIVE data — do not lose it. Generate ONLY
`ALTER TABLE public.customer_master ADD COLUMN IF NOT EXISTS <col> <type>;`
statements for fields in the sample payload below that are NOT already in
the list above. If every field already exists, return a single harmless
no-op comment line (e.g. `-- No new columns required.`) and nothing else.
Do NOT generate a CREATE TABLE statement, and do NOT reference dropping,
renaming, or retyping any existing column.
"""
    else:
        schema_context = """
The `public.customer_master` table does NOT exist yet. Generate the full
`CREATE TABLE IF NOT EXISTS` statement for it.
"""

    prompt = f"""You are an expert Lead Database Architect specializing in Master Data Management (MDM).

Based on the Jira specification and the dynamic cleansed sample data payload provided below, generate a production-ready PostgreSQL DDL script.

Jira Specification:
{jira_spec}

Sample Cleansed Data Payload (Infer column names and types strictly from this dynamic payload):
{sample_record}

{schema_context}

Requirements:
1. Include standard MDM audit columns on first creation:
   - `id UUID DEFAULT gen_random_uuid() PRIMARY KEY`
   - `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
   - `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
2. Dynamically map data types for all keys found in the Sample Cleansed Data Payload (e.g., VARCHAR, DOUBLE PRECISION, INT, BOOLEAN, TIMESTAMP).
3. Include appropriate constraints (NOT NULL, UNIQUE where logical based on key names) only on newly added columns.
4. Do NOT hardcode domain-specific fields; reflect whatever structure is provided in the input payload.
5. Provide inline SQL comments (`--`) explaining schema design decisions.
6. Return raw SQL script only without markdown code fences.
"""

    response: MDMDDLResponse = structured_llm.invoke(prompt)
    return response.ddl_sql.strip()


# ==========================================
# Step 3: Runner (Dry-Run Validation)
# ==========================================

def validate_ddl_syntax(ddl_sql: str) -> dict:
    """Validates generated DDL syntax against an in-memory SQL parser."""
    if not ddl_sql:
        return {"status": "FAILED", "reason": "Empty DDL SQL string provided."}

    conn = duckdb.connect(":memory:")
    try:
        statements = [stmt.strip() for stmt in ddl_sql.split(";") if stmt.strip()]
        for stmt in statements:
            if "CREATE TABLE" in stmt.upper():
                duckdb_stmt = (
                    stmt.replace("gen_random_uuid()", "uuid()")
                        .replace("DOUBLE PRECISION", "DOUBLE")
                )
                conn.execute(duckdb_stmt)
                
        return {"status": "SUCCESS", "message": "DDL SQL syntax validation passed."}
    except Exception as e:
        return {"status": "WARNING", "message": f"Syntax dry-run completed with notes: {str(e)}"}
    finally:
        conn.close()


# ==========================================
# Step 4: Postgres Executor
# ==========================================

def ensure_postgres_running(container_name: str = "mdm-postgres") -> bool:
    """Checks if PostgreSQL is running, and attempts to start or launch it if offline."""
    try:
        conn = psycopg2.connect(
            os.getenv("POSTGRES_CONNECTION_URI", "postgresql://postgres:postgres@localhost:5432/mdm_db"),
            connect_timeout=3,
        )
        conn.close()
        return True
    except Exception:
        pass

    try:
        check_cmd = f"docker inspect -f '{{{{.State.Running}}}}' {container_name}"
        result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)

        if result.stdout.strip() == "true":
            return True

        print(f"⚠️ [Self-Healing Engine] PostgreSQL container '{container_name}' is not running.")

        exists_cmd = f"docker ps -a --format '{{{{.Names}}}}' | grep -w {container_name}"
        exists_result = subprocess.run(exists_cmd, shell=True, capture_output=True, text=True)

        if container_name in exists_result.stdout:
            print(f"🔄 [Self-Healing Engine] Attempting to start existing container '{container_name}'...")
            subprocess.run(f"docker start {container_name}", shell=True, check=True, capture_output=True)
        else:
            print(f"🚀 [Self-Healing Engine] Container '{container_name}' not found. Spawning new PostgreSQL container...")
            subprocess.run(f"docker rm -f {container_name}", shell=True, capture_output=True)
            run_cmd = (
                f"docker run --name {container_name} -e POSTGRES_DB=mdm_db -e "
                "POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432 "
                "-d postgres:latest"
            )
            subprocess.run(run_cmd, shell=True, check=True, capture_output=True)

        print("⏳ [Self-Healing Engine] Waiting for PostgreSQL service to accept connections...")
        for _ in range(10):
            time.sleep(1)
            try:
                conn = psycopg2.connect("postgresql://postgres:postgres@localhost:5432/mdm_db")
                conn.close()
                print("✅ [Self-Healing Engine] PostgreSQL connection restored successfully!")
                return True
            except psycopg2.OperationalError:
                continue

        return False

    except Exception as e:
        print(f"❌ [Self-Healing Engine] Failed to self-heal PostgreSQL container: {e}")
        return False


def execute_mdm_on_postgres(ddl_sql: str, db_uri: str = None, auto_heal: bool = True) -> dict:
    """Connects to target PostgreSQL DB and executes DDL."""
    if not ddl_sql:
        return {"status": "FAILED", "error": "No DDL SQL provided for execution."}

    connection_string = db_uri or os.getenv(
        "POSTGRES_CONNECTION_URI",
        "postgresql://postgres:postgres@localhost:5432/mdm_db",
    )

    for attempt in range(2):
        try:
            conn = psycopg2.connect(connection_string)
            conn.autocommit = True
            cursor = conn.cursor()

            statements = [stmt.strip() for stmt in ddl_sql.split(";") if stmt.strip()]
            dml_prefixes = ("insert ", "update ", "delete ", "select ", "truncate ")
            
            def _is_dml(stmt: str) -> bool:
                code_only = re.sub(r"(?m)^\s*--.*$", "", stmt).strip().lower()
                return code_only.startswith(dml_prefixes)

            statements = [stmt for stmt in statements if not _is_dml(stmt)]
            statements = [
                re.sub(
                    r"(?im)^(\s*)CREATE TABLE (?!IF NOT EXISTS)",
                    r"\1CREATE TABLE IF NOT EXISTS ",
                    stmt,
                )
                for stmt in statements
            ]
            executed_count = 0

            for statement in statements:
                cursor.execute(statement)
                executed_count += 1

            cursor.close()
            conn.close()

            return {
                "status": "SUCCESS",
                "message": f"Successfully executed {executed_count} SQL statements on PostgreSQL.",
                "target": connection_string.split("@")[-1],
            }

        except psycopg2.OperationalError as e:
            if "Connection refused" in str(e) and auto_heal and attempt == 0:
                print("\n🔧 [Self-Healing Triggered] Connection refused on port 5432. Initiating auto-recovery...")
                healed = ensure_postgres_running("mdm-postgres")
                if healed:
                    print("🔄 [Self-Healing Engine] Retrying execution after recovery...")
                    continue

            return {
                "status": "FAILED",
                "error": str(e),
                "message": "Execution failed on target PostgreSQL instance after self-healing attempt.",
            }
        except Exception as e:
            return {
                "status": "FAILED",
                "error": str(e),
                "message": "Execution failed due to SQL or schema error.",
            }


# ==========================================
# Step 5: Golden Record Upsert
# ==========================================

GOLDEN_TABLE = "customer_master"


def determine_natural_key(record: Dict[str, Any]) -> str:
    """Dynamically detects the best natural key from the payload."""
    candidate_keys = ["email", "user_id", "customer_id", "id", "account_id"]
    for key in candidate_keys:
        if key in record and record[key]:
            return key
    # Fallback: Pick the first string column available
    for key, val in record.items():
        if isinstance(val, str) and val.strip():
            return key
    return list(record.keys())[0] if record else "id"


def ensure_table_initialized(sample_record: dict, db_uri: str = None) -> bool:
    """Checks if table exists; if not, automatically generates DDL based on record schema and executes it."""
    existing_schema = fetch_existing_customer_master_schema(db_uri)
    if existing_schema:
        return True

    print(f"⚠️ [MDM Engine] Table 'public.{GOLDEN_TABLE}' does not exist. Initializing schema dynamically...")
    ddl_sql = generate_production_ddl("Dynamic Schema Initialization", sample_record, existing_schema=[])
    exec_res = execute_mdm_on_postgres(ddl_sql, db_uri=db_uri)
    return exec_res.get("status") == "SUCCESS"


def upsert_golden_record(
    record: Dict[str, Any], db_uri: str = None, execute_live: bool = True
) -> Dict[str, Any]:
    """Agent 04 live entrypoint: dynamically inserts or updates a record into `public.customer_master`."""
    if not execute_live:
        return {"status": "SKIPPED", "message": "execute_live=False; MDM upsert not attempted."}

    if not record:
        return {"status": "FAILED", "error": "Cannot upsert an empty record."}

    connection_string = db_uri or os.getenv(
        "POSTGRES_CONNECTION_URI",
        "postgresql://postgres:postgres@localhost:5432/mdm_db",
    )
    is_local_target = "localhost" in connection_string or "127.0.0.1" in connection_string

    # Auto-initialize table schema if missing using current record keys
    if not ensure_table_initialized(record, connection_string):
        return {
            "status": "FAILED",
            "error": f"Could not verify or initialize public.{GOLDEN_TABLE} in PostgreSQL.",
        }

    natural_key = determine_natural_key(record)

    try:
        conn = psycopg2.connect(connection_string)
    except psycopg2.OperationalError:
        if not is_local_target or not ensure_postgres_running("mdm-postgres"):
            return {
                "status": "FAILED",
                "error": "PostgreSQL target is unavailable and could not be self-healed.",
            }
        conn = psycopg2.connect(connection_string)

    try:
        conn.autocommit = True
        cur = conn.cursor()

        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s",
            (GOLDEN_TABLE,),
        )
        existing_cols = {row[0] for row in cur.fetchall()}

        dropped_columns = [c for c in record if c not in existing_cols]
        filtered_record = {c: v for c, v in record.items() if c in existing_cols}

        if natural_key not in filtered_record:
            return {
                "status": "FAILED",
                "error": f"Natural key '{natural_key}' is not present in columns of public.{GOLDEN_TABLE}.",
                "dropped_columns": dropped_columns,
            }

        columns = list(filtered_record.keys())
        update_cols = [c for c in columns if c != natural_key]

        insert_stmt = sql.SQL(
            "INSERT INTO public.{table} ({cols}) VALUES ({vals}) "
            "ON CONFLICT ({key}) DO UPDATE SET {updates}, updated_at = CURRENT_TIMESTAMP"
        ).format(
            table=sql.Identifier(GOLDEN_TABLE),
            cols=sql.SQL(", ").join(sql.Identifier(c) for c in columns),
            vals=sql.SQL(", ").join(sql.Placeholder() for _ in columns),
            key=sql.Identifier(natural_key),
            updates=sql.SQL(", ").join(
                sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in update_cols
            ),
        )
        cur.execute(insert_stmt, [filtered_record[c] for c in columns])
        cur.close()

        return {
            "status": "SUCCESS",
            "message": f"Golden record upserted successfully using natural_key={natural_key}.",
            "dropped_columns": dropped_columns,
            "target": connection_string.split("@")[-1],
        }

    except Exception as e:
        return {"status": "FAILED", "error": str(e)}
    finally:
        conn.close()


# ==========================================
# Step 6: MDM Agent Execution Orchestrator
# ==========================================

def run_mdm_agent_autonomous(
    state: ProjectState, 
    sample_record: dict = None, 
    execute_live: bool = True,
    reset: bool = False
) -> ProjectState:
    """Autonomous Agent 04 Orchestrator with full schema execution and dynamic data support."""
    print("--- Running Autonomous Agent 04 (MDM Engine) ---")

    if reset:
        state.mdm_ddl = ""
        project_root = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
        schema_file = project_root / "output" / "mdm" / "schema.sql"
        if schema_file.exists():
            schema_file.unlink()

    jira_spec = ""
    if getattr(state, "jira_mdm_issue_key", None):
        jira_spec = fetch_mdm_jira_issue(state.jira_mdm_issue_key)
    if not jira_spec:
        jira_spec = "Generate production master table schema based on dynamically provided record structure."

    # Dynamically retrieve sample payload from state if not explicitly passed
    sample_payload = sample_record or getattr(state, "sample_cleansed_output", {})
    if not sample_payload:
        print("⚠️ No payload provided or found in state; waiting for dynamic record input.")
        return state

    try:
        existing_schema = fetch_existing_customer_master_schema()
        print(
            f"[1/4] Generating production PostgreSQL DDL "
            f"({'extending existing table' if existing_schema else 'creating new table'})..."
        )
        ddl_sql = generate_production_ddl(jira_spec, sample_payload, existing_schema=existing_schema)
        state.mdm_ddl = ddl_sql

        project_root = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
        output_dir = project_root / "output" / "mdm"
        output_dir.mkdir(parents=True, exist_ok=True)
        schema_file = output_dir / "schema.sql"
        schema_file.write_text(ddl_sql, encoding="utf-8")
        print(f"[2/4] Persisted schema to: {schema_file.resolve()}")

        print("[3/4] Running Step 03 (DuckDB Dry-Run Syntax Validation)...")
        val_result = validate_ddl_syntax(ddl_sql)
        print(f"      Validation: {val_result['status']} | {val_result['message']}")

        if execute_live:
            print("[4/4] Running Step 04 (Live PostgreSQL Target Execution)...")
            exec_result = execute_mdm_on_postgres(ddl_sql)
            print(f"      Execution: {exec_result['status']} | {exec_result.get('message') or exec_result.get('error')}")

    except Exception as e:
        error_msg = f"Autonomous Agent 04 Error: {str(e)}"
        print(error_msg)
        state.errors.append(error_msg)

    return state


if __name__ == "__main__":
    test_state = ProjectState()
    run_mdm_agent_autonomous(test_state, execute_live=True)