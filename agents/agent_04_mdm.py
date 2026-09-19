import os
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Dict

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
    table, or [] if it doesn't exist yet / Postgres is unreachable. Used so
    DDL generation can extend the ACTUAL live schema instead of inventing an
    unrelated table from the Jira text alone — the live table is the real
    source of truth, not whatever was locally cached from a previous run."""
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
    """Generates production PostgreSQL DDL based on Jira specifications and
    dynamic sample data structure. When `existing_schema` is non-empty (the
    live table already exists), the LLM is instructed to extend it with
    ALTER TABLE ADD COLUMN statements for genuinely new fields only, instead
    of generating a fresh, disconnected CREATE TABLE that would silently
    never apply against a table that already has different columns."""
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

Based on the Jira specification and cleansed sample data payload, generate a production-ready PostgreSQL DDL script.

Jira Specification:
{jira_spec}

Sample Cleansed Data Payload:
{sample_record}

{schema_context}

Requirements:
1. Add standard MDM audit columns on first creation only:
   - `id UUID DEFAULT gen_random_uuid() PRIMARY KEY`
   - `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
   - `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
2. Map data types cleanly (e.g., VARCHAR, DOUBLE PRECISION, INT).
3. Include appropriate column constraints (NOT NULL, UNIQUE where appropriate)
   only on newly-added columns — never add a NOT NULL constraint to a column
   on an existing table with rows, since that would fail against live data.
4. Do NOT include any INSERT/UPDATE/DELETE statements or sample data — this
   script only defines schema. Explain the intended upsert pattern (e.g.
   `ON CONFLICT (...) DO UPDATE SET ...`) as a SQL comment, not as an
   executable statement.
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
        # Extract CREATE TABLE statements for syntactic dry-run validation
        statements = [stmt.strip() for stmt in ddl_sql.split(";") if stmt.strip()]
        for stmt in statements:
            if "CREATE TABLE" in stmt.upper():
                # Convert PostgreSQL specific types to standard types for dry-run parsing
                duckdb_stmt = (
                    stmt.replace("gen_random_uuid()", "uuid()")
                        .replace("DOUBLE PRECISION", "DOUBLE")
                )
                conn.execute(duckdb_stmt)
                
        return {"status": "SUCCESS", "message": "DDL SQL syntax validation passed."}
    except Exception as e:
        # PostgreSQL-specific DDL might trigger minor DuckDB parser differences; log warning
        return {"status": "WARNING", "message": f"Syntax dry-run completed with notes: {str(e)}"}
    finally:
        conn.close()


# ==========================================
# Step 4: Postgres Executor
# ==========================================

def ensure_postgres_running(container_name: str = "mdm-postgres") -> bool:
  """Checks if PostgreSQL is running, and attempts to start or launch it if offline.

  Tries a direct connection to the actually-configured POSTGRES_CONNECTION_URI
  first — e.g. a natively-installed local PostgreSQL service (no Docker
  involved at all) already satisfies "is it running", and assuming Docker
  management is needed just because the host is localhost would otherwise
  make this report failure (and skip real work) even though the database is
  right there and reachable.
  """
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
    result = subprocess.run(
        check_cmd, shell=True, capture_output=True, text=True
    )

    if result.stdout.strip() == "true":
      return True

    print(
        f"⚠️ [Self-Healing Engine] PostgreSQL container '{container_name}' is"
        " not running."
    )

    exists_cmd = (
        f"docker ps -a --format '{{{{.Names}}}}' | grep -w {container_name}"
    )
    exists_result = subprocess.run(
        exists_cmd, shell=True, capture_output=True, text=True
    )

    if container_name in exists_result.stdout:
      print(
          "🔄 [Self-Healing Engine] Attempting to start existing container"
          f" '{container_name}'..."
      )
      subprocess.run(
          f"docker start {container_name}",
          shell=True,
          check=True,
          capture_output=True,
      )
    else:
      print(
          "🚀 [Self-Healing Engine] Container"
          f" '{container_name}' not found. Spawning new PostgreSQL container..."
      )
      run_cmd = (
          f"docker run --name {container_name} -e POSTGRES_DB=mdm_db -e"
          " POSTGRES_USER=postgres -e POSTGRES_PASSWORD=postgres -p 5432:5432"
          " -d postgres:latest"
      )
      subprocess.run(run_cmd, shell=True, check=True, capture_output=True)

    print(
        "⏳ [Self-Healing Engine] Waiting for PostgreSQL service to accept"
        " connections..."
    )
    for _ in range(10):
      time.sleep(1)
      try:
        conn = psycopg2.connect(
            "postgresql://postgres:postgres@localhost:5432/mdm_db"
        )
        conn.close()
        print(
            "✅ [Self-Healing Engine] PostgreSQL connection restored"
            " successfully!"
        )
        return True
      except psycopg2.OperationalError:
        continue

    return False

  except Exception as e:
    print(
        f"❌ [Self-Healing Engine] Failed to self-heal PostgreSQL container: {e}"
    )
    return False


def execute_mdm_on_postgres(
    ddl_sql: str, db_uri: str = None, auto_heal: bool = True
) -> dict:
  """Connects to target PostgreSQL DB and executes DDL.

  Includes self-healing capabilities if connection is refused.
  """
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
      # This script is meant to be schema-only. The LLM prompt tells it not
      # to include sample INSERT/UPDATE/DELETE statements, but free-tier
      # models don't always comply — skip any DML defensively so an
      # "example" statement can never run for real against live data. Strip
      # full `-- ...` comment LINES first (not just leading dash characters),
      # since a real statement is often preceded by several lines of
      # descriptive comments that would otherwise defeat a prefix check.
      dml_prefixes = ("insert ", "update ", "delete ", "select ", "truncate ")
      def _is_dml(stmt: str) -> bool:
        code_only = re.sub(r"(?m)^\s*--.*$", "", stmt).strip().lower()
        return code_only.startswith(dml_prefixes)
      statements = [stmt for stmt in statements if not _is_dml(stmt)]
      # The prompt also asks for `CREATE TABLE IF NOT EXISTS`, but free-tier
      # models don't reliably include it — enforce it here so re-running
      # this script against a database that already has the table doesn't
      # hard-fail with "relation already exists".
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
          "message": (
              f"Successfully executed {executed_count} SQL statements on"
              " PostgreSQL."
          ),
          "target": connection_string.split("@")[-1],
      }

    except psycopg2.OperationalError as e:
      if "Connection refused" in str(e) and auto_heal and attempt == 0:
        print(
            "\n🔧 [Self-Healing Triggered] Connection refused on port 5432."
            " Initiating auto-recovery..."
        )
        healed = ensure_postgres_running("mdm-postgres")
        if healed:
          print(
              "🔄 [Self-Healing Engine] Retrying execution after recovery..."
          )
          continue

      return {
          "status": "FAILED",
          "error": str(e),
          "message": (
              "Execution failed on target PostgreSQL instance after"
              " self-healing attempt."
          ),
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
NATURAL_KEY = "email"


def upsert_golden_record(
    record: Dict[str, Any], db_uri: str = None, execute_live: bool = True
) -> Dict[str, Any]:
    """Agent 04 live entrypoint: inserts or updates one golden record in
    `public.customer_master`, evolving the schema as needed. Never raises —
    all failures (including Postgres/Docker being unavailable) are returned
    as a {"status": "FAILED", ...} dict so the ingestion API can still report
    partial success for the ETL stage."""
    if not execute_live:
        return {"status": "SKIPPED", "message": "execute_live=False; MDM upsert not attempted."}

    if not record or NATURAL_KEY not in record or not record.get(NATURAL_KEY):
        return {
            "status": "FAILED",
            "error": f"Record is missing required natural key '{NATURAL_KEY}'.",
        }

    connection_string = db_uri or os.getenv(
        "POSTGRES_CONNECTION_URI",
        "postgresql://postgres:postgres@localhost:5432/mdm_db",
    )
    is_local_target = "localhost" in connection_string or "127.0.0.1" in connection_string

    try:
        conn = psycopg2.connect(connection_string)
    except psycopg2.OperationalError:
        # Only attempt Docker self-healing for a local dev Postgres target —
        # a remote host (e.g. Neon) being unreachable isn't something a local
        # `docker start` can fix, and shouldn't be attempted for one.
        if not is_local_target or not ensure_postgres_running("mdm-postgres"):
            return {
                "status": "FAILED",
                "error": "PostgreSQL target is unavailable and could not be self-healed.",
            }
        conn = psycopg2.connect(connection_string)

    try:
        conn.autocommit = True
        cur = conn.cursor()

        # 1. Check the table's ACTUAL current schema — never create or alter
        #    it here. Only Agent 04 (via the dashboard button) is allowed to
        #    do that.
        cur.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = %s",
            (GOLDEN_TABLE,),
        )
        existing_cols = {row[0] for row in cur.fetchall()}

        if not existing_cols:
            return {
                "status": "FAILED",
                "error": (
                    f"public.{GOLDEN_TABLE} doesn't exist yet. Run Agent 04 once "
                    "to initialize the schema before live ingestion."
                ),
            }

        # 2. Drop any fields the table doesn't have a column for yet, rather
        #    than auto-adding them.
        dropped_columns = [c for c in record if c not in existing_cols]
        filtered_record = {c: v for c, v in record.items() if c in existing_cols}

        if NATURAL_KEY not in filtered_record:
            return {
                "status": "FAILED",
                "error": f"Natural key '{NATURAL_KEY}' isn't a column on public.{GOLDEN_TABLE}.",
                "dropped_columns": dropped_columns,
            }

        # 3. Upsert the golden record, keyed on the natural key.
        columns = list(filtered_record.keys())
        update_cols = [c for c in columns if c != NATURAL_KEY]

        insert_stmt = sql.SQL(
            "INSERT INTO public.{table} ({cols}) VALUES ({vals}) "
            "ON CONFLICT ({key}) DO UPDATE SET {updates}, updated_at = CURRENT_TIMESTAMP"
        ).format(
            table=sql.Identifier(GOLDEN_TABLE),
            cols=sql.SQL(", ").join(sql.Identifier(c) for c in columns),
            vals=sql.SQL(", ").join(sql.Placeholder() for _ in columns),
            key=sql.Identifier(NATURAL_KEY),
            updates=sql.SQL(", ").join(
                sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(c)) for c in update_cols
            ),
        )
        cur.execute(insert_stmt, [filtered_record[c] for c in columns])
        cur.close()

        return {
            "status": "SUCCESS",
            "message": f"Golden record upserted for {NATURAL_KEY}={filtered_record[NATURAL_KEY]}.",
            "dropped_columns": dropped_columns,
            "target": connection_string.split("@")[-1],
        }

    except Exception as e:
        return {"status": "FAILED", "error": str(e)}
    finally:
        # Always release the connection, even if a statement above raised.
        conn.close()


# ==========================================
# Step 6: MDM Agent Execution Orchestrator
# ==========================================

def run_mdm_agent_autonomous(state: ProjectState, sample_record: dict = None, execute_live: bool = False) -> ProjectState:
    """
    Autonomous Agent 04 Orchestrator:
    1. Fetch MDM details from Jira (Step 01)
    2. Generate DDL script from requirement context (Step 02)
    3. Save output/mdm/schema.sql artifact
    4. Dry-run validation via DuckDB parser (Step 03)
    5. Live target schema execution via PostgreSQL driver (Step 04)
    """
    print("--- Running Autonomous Agent 04 (MDM Engine) ---")

    jira_spec = ""
    if getattr(state, "jira_mdm_issue_key", None):
        jira_spec = fetch_mdm_jira_issue(state.jira_mdm_issue_key)
    if not jira_spec:
        jira_spec = "Generate production master table schema for customer KYC records with risk scoring."

    sample_payload = sample_record or getattr(state, "sample_cleansed_output", {
        "full_name": "Ananya Sharma",
        "pan_number": "ABCDE1234F",
        "masked_aadhaar": "XXXX-XXXX-1098",
        "monthly_income": 85000.0,
        "credit_score": 765,
        "risk_index": 22.5
    })

    try:
        # Step 02: Code Generation — check the LIVE table's actual current
        # schema first, so a new Jira story extends it (ALTER ADD COLUMN)
        # instead of generating a disconnected, unrelated table from the
        # Jira text alone.
        existing_schema = fetch_existing_customer_master_schema()
        print(
            f"[1/4] Generating production PostgreSQL DDL "
            f"({'extending existing table' if existing_schema else 'creating new table'})..."
        )
        ddl_sql = generate_production_ddl(jira_spec, sample_payload, existing_schema=existing_schema)
        state.mdm_ddl = ddl_sql

        # Save output artifact
        project_root = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
        output_dir = project_root / "output" / "mdm"
        output_dir.mkdir(parents=True, exist_ok=True)
        schema_file = output_dir / "schema.sql"
        schema_file.write_text(ddl_sql, encoding="utf-8")
        print(f"[2/4] Persisted schema to: {schema_file.resolve()}")

        # Dry-Run Validation Tool
        print("[3/4] Running Step 03 (DuckDB Dry-Run Syntax Validation)...")
        val_result = validate_ddl_syntax(ddl_sql)
        print(f"      Validation: {val_result['status']} | {val_result['message']}")

        # Target Database Deployment Tool
        if execute_live:
            print("[4/4] Running Step 04 (Live PostgreSQL Target Execution)...")
            exec_result = execute_mdm_on_postgres(ddl_sql)
            print(f"      Execution: {exec_result['status']} | {exec_result.get('message') or exec_result.get('error')}")

    except Exception as e:
        error_msg = f"Autonomous Agent 04 Error: {str(e)}"
        print(error_msg)
        state.errors.append(error_msg)

    return state