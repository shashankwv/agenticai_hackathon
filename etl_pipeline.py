import re
from pathlib import Path
import duckdb

def mask_aadhaar(aadhaar_str: str) -> str:
    if not aadhaar_str:
        return "XXXX-XXXX-XXXX"
    digits = re.sub(r'\D', '', str(aadhaar_str))
    if len(digits) >= 4:
        return f"XXXX-XXXX-{digits[-4:]}"
    return "XXXX-XXXX-XXXX"

def calculate_risk_index(monthly_income, credit_score) -> float:
    try:
        inc = float(monthly_income) if monthly_income is not None else 0.0
    except (ValueError, TypeError):
        inc = 0.0
    try:
        cs = float(credit_score) if credit_score is not None else 600.0
    except (ValueError, TypeError):
        cs = 600.0
    score_factor = max(0.0, min(1.0, (850.0 - cs) / 550.0))
    income_factor = 1.0 if inc < 25000 else (0.5 if inc < 75000 else 0.1)
    return round((score_factor * 0.7 + income_factor * 0.3) * 100, 2)

def transform_batch(raw_records: list) -> list:
    cleansed = []
    for rec in raw_records:
        cleaned_rec = {}
        for k, v in rec.items():
            cleaned_rec[k] = v.strip() if isinstance(v, str) else v
        aadhaar_val = cleaned_rec.get("aadhaar_no") or cleaned_rec.get("aadhaar") or ""
        cleaned_rec["aadhaar_no"] = mask_aadhaar(aadhaar_val)
        inc = cleaned_rec.get("monthly_income")
        cs = cleaned_rec.get("credit_score")
        cleaned_rec["risk_index"] = calculate_risk_index(inc, cs)
        cleansed.append(cleaned_rec)
    return cleansed

def process_and_store_kyc(form_data: dict) -> dict:
    cleansed = transform_batch([form_data])[0]
    db_path = Path(__file__).resolve().parent / 'staging.duckdb'
    conn = duckdb.connect(str(db_path))
    keys = list(cleansed.keys())
    cols = ", ".join([f'"{k}"' for k in keys])
    placeholders = ", ".join(["?"] * len(keys))
    vals = [cleansed[k] for k in keys]
    create_cols = ", ".join([f'"{k}" VARCHAR' for k in keys])
    conn.execute(f"CREATE TABLE IF NOT EXISTS cleansed_staging_data ({create_cols})")
    conn.execute(f"INSERT INTO cleansed_staging_data ({cols}) VALUES ({placeholders})", vals)
    conn.close()
    return {"status": "success", "message": "KYC record successfully processed and stored."}