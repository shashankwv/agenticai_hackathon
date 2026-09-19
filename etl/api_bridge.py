import os
import json
import duckdb
import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pathlib import Path

app = FastAPI()
DB_PATH = Path(__file__).resolve().parent / "etl.duckdb"

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

@app.post("/api/ingest")
async def ingest_payload(data: dict):
    try:
        con = get_db_connection()
        
        # Ensure table exists & handle dynamic field additions
        ensure_landing_table_and_schema(con, data)

        record_id = data.get("id") or data.get("email") or "generated_id"
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

        return {"status": "success", "message": "Payload ingested successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ingestion failed: {e}")

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run("etl.api_bridge:app", host="127.0.0.1", port=8000, reload=True)