import json
import duckdb
from typing import Dict, Any
from fastapi import FastAPI, HTTPException
from pathlib import Path
from agents.agent_04_mdm.step_03_agent import run_mdm_agent_autonomous
from core.state import ProjectState
import traceback
from agents.agent_03_etl.step_03_runner import run_etl_in_duckdb

app = FastAPI(title="Dynamic UI to ETL/MDM Data Bridge")
DUCKDB_PATH = Path(__file__).resolve().parent / "staging.duckdb"

@app.post("/api/submit-registration")
@app.post("/api/ingest")
def ingest_dynamic_ui_data(payload: Dict[str, Any]):
    if not payload:
        raise HTTPException(status_code=400, detail="Empty payload received")

    try:
        # 1. Store raw payload in landing table
        conn = duckdb.connect(str(DUCKDB_PATH))
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ui_raw_ingestion (
                id UUID DEFAULT gen_random_uuid(),
                raw_payload JSON,
                ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.execute(
            "INSERT INTO ui_raw_ingestion (raw_payload) VALUES (?)",
            [json.dumps(payload)]
        )
        conn.close()

        # 2. AUTOMATICALLY TRIGGER AGENT 03 (ETL & Schema Evolution)
        # Pass payload directly to Agent 03 to evolve DuckDB schema & populate cleansed_staging_data
        etl_code = """
def transform_batch(raw_records: list) -> list:
    cleansed_records = []
    for record in raw_records:
        if isinstance(record, dict):
            cleansed_records.append(dict(record))
    return cleansed_records
"""
        run_etl_in_duckdb(etl_code, [payload], db_path=str(DUCKDB_PATH))
        print("[Agent 03] Automatically populated & evolved cleansed_staging_data!")

        return {"status": "success", "message": "Ingested and cleansed via Agent 03!"}

    except Exception as e:
        # Capture and print the full error to stdout and return it to UI
        error_details = traceback.format_exc()
        print("\n=== EXACT API BRIDGE ERROR ===")
        print(error_details)
        print("===============================\n")
        
        raise HTTPException(
            status_code=500, 
            detail={"error": str(e), "traceback": error_details.splitlines()}
        )

