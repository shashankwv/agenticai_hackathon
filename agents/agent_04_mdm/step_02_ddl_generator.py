import os

import psycopg2
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from core.llm_factory import get_llm

load_dotenv()


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
