import re
import logging
import duckdb
import pandas as pd

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def sanitize_aadhaar(val):
    if not val:
        return None
    cleaned_str = re.sub('[^0-9]', '', str(val).strip())
    if len(cleaned_str) == 12:
        return cleaned_str
    return None

def mask_aadhaar(aadhaar_str):
    sanitized = sanitize_aadhaar(aadhaar_str)
    if not sanitized:
        return "XXXX-XXXX-XXXX"
    return f"XXXX-XXXX-{sanitized[-4:]}"

def calculate_risk_index(credit_score, income):
    try:
        cs = float(credit_score) if credit_score is not None else 650.0
        inc = float(income) if income is not None else 50000.0
        if cs <= 0:
            cs = 300.0
        cs_factor = max(0.0, min(1.0, cs / 850.0))
        inc_factor = max(0.0, min(1.0, inc / 200000.0))
        risk = round(100.0 - (cs_factor * 60.0) - (inc_factor * 40.0), 2)
        return max(0.0, min(100.0, risk))
    except (ValueError, TypeError):
        return 50.0

def transform_batch(raw_records: list) -> list:
    cleansed_records = []
    for rec in raw_records:
        cleaned = {}
        for k, v in rec.items():
            if isinstance(v, str):
                cleaned[k] = v.strip()
            else:
                cleaned[k] = v
        raw_aadhaar = cleaned.get("aadhaar_no") or cleaned.get("aadhaar")
        sanitized_a = sanitize_aadhaar(raw_aadhaar)
        cleaned["aadhaar_sanitized"] = sanitized_a
        cleaned["aadhaar_masked"] = mask_aadhaar(raw_aadhaar)
        credit_score = cleaned.get("credit_score")
        income = cleaned.get("annual_income") or cleaned.get("income")
        cleaned["risk_index"] = calculate_risk_index(credit_score, income)
        cleansed_records.append(cleaned)
    return cleansed_records

def process_and_store_kyc(form_data: dict) -> dict:
    transformed = transform_batch([form_data])[0]
    conn = duckdb.connect('staging.duckdb')
    try:
        df = pd.DataFrame([transformed])
        conn.execute("CREATE TABLE IF NOT EXISTS kyc_staging AS SELECT * FROM df WHERE 1=0")
        conn.register("temp_df", df)
        conn.execute("INSERT INTO kyc_staging SELECT * FROM temp_df")
        logger.info(f"Successfully processed KYC for customer with Aadhaar Masked: {transformed.get('aadhaar_masked')}")
        return {"status": "success", "message": "KYC record successfully processed and stored."}
    except Exception as e:
        logger.error(f"Failed to process KYC record: {e}")
        return {"status": "error", "message": str(e)}
    finally:
        conn.close()
