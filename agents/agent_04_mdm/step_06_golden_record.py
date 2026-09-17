# agents/agent_04_mdm/step_06_golden_record.py
"""Live, per-record MDM ingestion path.

step_02_ddl_generator.py / step_03_agent.py handle the Jira-ticket-driven
"generate/extend the customer_master DDL from an LLM and run it" flow used by
the Streamlit dashboard's "Run Agent 04" button — that's the ONLY place
`public.customer_master`'s schema is created or altered.

This module is the counterpart used by the live HTTP ingestion path
(api_bridge.py): given one already-cleansed record (produced by Agent 03), it
upserts it as the customer's "golden copy", keyed on `email`, into whatever
schema Agent 04 has already established. It never creates or alters the
table — a field the table doesn't have a column for yet is silently dropped
from the golden record (see `dropped_columns` in the result) rather than
being auto-added, so schema changes stay an explicit, reviewable action
instead of something any live request can trigger.
"""
import os
from typing import Any, Dict

import psycopg2
from dotenv import load_dotenv
from psycopg2 import sql

from agents.agent_04_mdm.step_05_postgres_executor import ensure_postgres_running

load_dotenv()

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
