import os
import json
import re
import uuid
import duckdb
import uvicorn
import psycopg2
from psycopg2 import sql
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

app = FastAPI()
DB_PATH = Path(__file__).resolve().parent / "etl.duckdb"
POSTGRES_URI = os.getenv(
    "POSTGRES_CONNECTION_URI",
    "postgresql://postgres:postgres@localhost:5432/mdm",
)

def get_db_connection():
    return duckdb.connect(str(DB_PATH))

def ensure_landing_table_and_schema(con: duckdb.DuckDBPyConnection, payload: dict):
    """
    Creates table dynamically on 'Start Fresh' and handles incremental changes.
    """
    # 1. Ensure table exists with standard columns
    con.execute("""
        CREATE TABLE IF NOT EXISTS landing_ui (
            id VARCHAR PRIMARY KEY,
            ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            payload JSON
        );
    """)

    # 2. Get existing table columns
    existing_cols = {row[0] for row in con.execute("DESCRIBE landing_ui").fetchall()}

    # 3. Handle incremental changes by dynamically adding new columns
    for key in payload.keys():
        if key not in existing_cols and key not in ["id", "ingested_at", "payload"]:
            con.execute(f'ALTER TABLE landing_ui ADD COLUMN "{key}" VARCHAR;')


def persist_to_postgres(data: dict) -> str:
    """Promote the validated KYC payload into the PostgreSQL golden table."""
    name = str(data.get("full_name") or "").strip()
    phone = str(data.get("phone_number") or "").strip()
    ssn = re.sub(r"\D", "", str(data.get("ssn") or ""))
    if not name or not phone or not ssn:
        raise ValueError("full_name, phone_number, and ssn are required for PostgreSQL persistence")
    if len(ssn) != 9:
        raise ValueError("ssn must contain exactly 9 digits for customer_master.gov_id_ssn")

    load_id = str(data.get("load_id") or data.get("batch_id") or uuid.uuid4())
    marital_status = str(data.get("marital_status") or "").strip() or None

    # Agent 04 regenerates customer_master, so its optional lineage/MDM columns
    # come and go between runs. Only write the columns the live table has.
    candidate_values = {
        "party_legal_name": name,
        "contact_phone": phone,
        "gov_id_ssn": ssn,
        "marital_status": marital_status,
        "source_system": "CORE_BANKING_UI",
        "load_id": load_id,
        "source_priority": 100,
        "match_confidence": 1.0,
        "match_rule_applied": "EXACT_SSN",
    }

    conn = psycopg2.connect(POSTGRES_URI)
    try:
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = 'customer_master'"
            )
            live_cols = {row[0] for row in cur.fetchall()}
            if not live_cols:
                raise ValueError("public.customer_master does not exist; run Agent 04 first")

            values = {col: val for col, val in candidate_values.items() if col in live_cols}
            update_cols = [col for col in values if col != "gov_id_ssn"]
            set_clauses = [
                sql.SQL("{c} = EXCLUDED.{c}").format(c=sql.Identifier(col)) for col in update_cols
            ]
            if "updated_at" in live_cols:
                set_clauses.append(sql.SQL("updated_at = CURRENT_TIMESTAMP"))

            query = sql.SQL(
                "INSERT INTO public.customer_master ({cols}) VALUES ({vals}) "
                "ON CONFLICT (gov_id_ssn) DO UPDATE SET {sets} RETURNING id"
            ).format(
                cols=sql.SQL(", ").join(map(sql.Identifier, values)),
                vals=sql.SQL(", ").join(sql.Placeholder() * len(values)),
                sets=sql.SQL(", ").join(set_clauses),
            )
            cur.execute(query, list(values.values()))
            return str(cur.fetchone()[0])
    finally:
        conn.close()

@app.post("/api/ingest")
async def ingest_payload(data: dict):
    try:
        con = get_db_connection()
        
        # Ensure table exists & handle dynamic field additions
        ensure_landing_table_and_schema(con, data)

        record_id = str(data.get("id") or data.get("email") or uuid.uuid4())
        payload_json = json.dumps(data)

        # Build dynamic INSERT query matching standard + dynamic fields
        existing_cols = [row[0] for row in con.execute("DESCRIBE landing_ui").fetchall()]
        insert_cols = ["id", "payload"]
        insert_vals = [record_id, payload_json]

        for col in existing_cols:
            if col not in ["id", "ingested_at", "payload"]:
                insert_cols.append(f'"{col}"')
                insert_vals.append(str(data.get(col, "")))

        cols_str = ", ".join(insert_cols)
        placeholders = ", ".join(["?"] * len(insert_vals))

        con.execute(f"INSERT INTO landing_ui ({cols_str}) VALUES ({placeholders})", insert_vals)
        con.close()

        record_id = persist_to_postgres(data)
        return {
            "status": "success",
            "message": "Payload ingested into DuckDB and PostgreSQL customer_master",
            "record_id": record_id,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("etl.api_bridge:app", host="127.0.0.1", port=8000, reload=True)