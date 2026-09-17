import json
import sys
import traceback
from pathlib import Path
from typing import Any, Dict

import duckdb
from fastapi import FastAPI, HTTPException

# Agent 04's self-healing logs use emoji; Windows consoles default to cp1252,
# which raises UnicodeEncodeError on print() and crashes the whole request.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from agents.agent_03_etl.agent_03_etl import process_ingested_payload
from agents.agent_04_mdm.step_06_golden_record import upsert_golden_record

app = FastAPI(title="Dynamic UI to ETL/MDM Data Bridge")
DUCKDB_PATH = Path(__file__).resolve().parent / "staging.duckdb"

# Maps the React UI's camelCase FormData fields (frontend-ui/src/App.tsx) to
# the canonical snake_case field names Agents 03/04 operate on. Without this,
# the UI's `aadhaarNumber`/`fullName`/`calculatedCreditScore` never line up
# with ETL/MDM's `aadhaar_no`/`full_name`/`credit_score`.
UI_FIELD_MAP = {
    "fullName": "full_name",
    "dob": "dob",
    "email": "email",
    "phone": "phone",
    "aadhaarNumber": "aadhaar_no",
    "addressLine1": "address_line1",
    "addressLine2": "address_line2",
    "city": "city",
    "state": "state",
    "pincode": "pincode",
    "employmentType": "employment_type",
    "annualIncome": "annual_income",
    "calculatedCreditScore": "credit_score",
    "termsAccepted": "terms_accepted",
}


def normalize_ui_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    return {UI_FIELD_MAP.get(key, key): value for key, value in payload.items()}


@app.post("/api/submit-registration")
@app.post("/api/ingest")
def ingest_dynamic_ui_data(payload: Dict[str, Any]):
    if not payload:
        raise HTTPException(status_code=400, detail="Empty payload received")

    try:
        # 1. Store the raw payload in a landing/audit table, untouched.
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
            [json.dumps(payload)],
        )
        conn.close()

        canonical_record = normalize_ui_payload(payload)

        # 2. Agent 03: cleanse (mask Aadhaar, compute risk_index) and persist
        #    into DuckDB's cleansed_staging_data, evolving schema as needed.
        etl_result = process_ingested_payload(canonical_record, db_filename=str(DUCKDB_PATH))
        cleansed_record = etl_result.get("sample_output") or canonical_record

        # 3. Agent 04: upsert the cleansed record as the golden copy in
        #    PostgreSQL's public.customer_master, evolving schema as needed.
        mdm_result = upsert_golden_record(cleansed_record)

        overall_status = "success" if mdm_result.get("status") == "SUCCESS" else "partial_success"

        return {
            "status": overall_status,
            "message": (
                "Ingested, cleansed via Agent 03, and upserted golden record via Agent 04."
                if overall_status == "success"
                else "Ingested and cleansed via Agent 03, but Agent 04 MDM upsert failed "
                "(see mdm_result)."
            ),
            "etl_result": etl_result,
            "mdm_result": mdm_result,
        }

    except Exception as e:
        error_details = traceback.format_exc()
        print("\n=== EXACT API BRIDGE ERROR ===")
        print(error_details)
        print("===============================\n")

        raise HTTPException(
            status_code=500,
            detail={"error": str(e), "traceback": error_details.splitlines()},
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api_bridge:app", host="0.0.0.0", port=8000, reload=True)
