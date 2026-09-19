import json
import re
import duckdb
import pandas as pd
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "etl.duckdb"
AADHAAR_RE = re.compile(r"^\d{12}$")
STG_COLS = ["id", "aadhaar_no", "aadhaar_masked", "credit_score", "monthly_income", "credit_history", "risk_index", "status", "error_code"]


def mask_sensitive_value(val: str, keep_last: int = 4) -> str:
    digits = re.sub(r"\D", "", str(val or ""))
    tail = digits[-keep_last:] if keep_last > 0 and digits else ""
    full = "X" * max(len(digits) - len(tail), 0) + tail
    if not full:
        return "X" * max(keep_last, 4)
    return "-".join(full[i:i + 4] for i in range(0, len(full), 4))


def sanitize_aadhaar(raw):
    if raw is None or str(raw).strip() == "":
        return "", "E001_MISSING_AADHAAR"
    digits = re.sub(r"\D", "", str(raw))
    if not AADHAAR_RE.match(digits):
        return digits, "E002_INVALID_AADHAAR_FORMAT"
    return digits, None


def normalize_credit_score(score):
    try:
        s = int(float(score))
    except (TypeError, ValueError):
        return None, "E003_INVALID_CREDIT_SCORE"
    return min(max(s, 300), 900), None


def compute_risk_index(monthly_income, credit_history) -> float:
    try:
        income = float(monthly_income or 0)
    except (TypeError, ValueError):
        income = 0.0
    hist = str(credit_history or "unknown").strip().lower()
    hist_score = {"excellent": 10, "good": 30, "fair": 55, "poor": 80, "none": 70}.get(hist, 60)
    income_score = 80 if income < 15000 else 55 if income < 40000 else 30 if income < 100000 else 10
    return round(0.5 * income_score + 0.5 * hist_score, 2)


def transform_batch(raw_records: list[dict]) -> list[dict]:
    out = []
    for rec in raw_records:
        aadhaar, err = sanitize_aadhaar(rec.get("aadhaar_no"))
        score, score_err = normalize_credit_score(rec.get("credit_score"))
        err = err or score_err
        try:
            income = float(rec.get("monthly_income")) if rec.get("monthly_income") is not None else None
        except (TypeError, ValueError):
            income = None
        out.append({
            "id": str(rec.get("id", "")), "aadhaar_no": aadhaar if not err else None,
            "aadhaar_masked": mask_sensitive_value(aadhaar), "credit_score": score,
            "monthly_income": income, "credit_history": rec.get("credit_history"),
            "risk_index": compute_risk_index(income, rec.get("credit_history")),
            "status": "rejected" if err else "ok", "error_code": err,
        })
    return out


def run_pipeline():
    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE TABLE IF NOT EXISTS landing_ui (id VARCHAR, ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, payload JSON);")
    con.execute("CREATE TABLE IF NOT EXISTS staging_ui (id VARCHAR, aadhaar_no VARCHAR, aadhaar_masked VARCHAR, credit_score INTEGER, monthly_income DOUBLE, credit_history VARCHAR, risk_index DOUBLE, status VARCHAR, error_code VARCHAR, transformed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")
    con.execute("CREATE TABLE IF NOT EXISTS customer_master (id VARCHAR, aadhaar_no VARCHAR, credit_score INTEGER, risk_index DOUBLE, loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")
    con.execute("CREATE TABLE IF NOT EXISTS quarantine_ui (id VARCHAR, aadhaar_masked VARCHAR, error_code VARCHAR, quarantined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")
    rows = con.execute("SELECT id, payload FROM landing_ui").fetchall()
    raw_records = []
    for rid, payload in rows:
        data = json.loads(payload) if isinstance(payload, str) else (payload or {})
        data.setdefault("id", rid)
        raw_records.append(data)
    transformed = transform_batch(raw_records)
    if not transformed:
        print("landing_ui empty; nothing to transform")
        con.close()
        return
    df = pd.DataFrame(transformed, columns=STG_COLS)
    con.register("stg_df", df)
    con.execute("INSERT INTO staging_ui (id, aadhaar_no, aadhaar_masked, credit_score, monthly_income, credit_history, risk_index, status, error_code) SELECT id, aadhaar_no, aadhaar_masked, TRY_CAST(credit_score AS INTEGER), TRY_CAST(monthly_income AS DOUBLE), credit_history, risk_index, status, error_code FROM stg_df")
    con.execute("INSERT INTO customer_master (id, aadhaar_no, credit_score, risk_index) SELECT id, aadhaar_no, TRY_CAST(credit_score AS INTEGER), risk_index FROM stg_df WHERE status = 'ok'")
    con.execute("INSERT INTO quarantine_ui (id, aadhaar_masked, error_code) SELECT id, aadhaar_masked, error_code FROM stg_df WHERE status = 'rejected'")
    con.unregister("stg_df")
    ok = int((df["status"] == "ok").sum())
    rejected = len(df) - ok
    for r in transformed[:5]:
        print(f"id={r['id']} aadhaar={r['aadhaar_masked']} score={r['credit_score']} risk={r['risk_index']} status={r['status']} err={r['error_code']}")
    print(f"Summary: read={len(rows)} staged={len(df)} loaded_customer_master={ok} quarantined={rejected}")
    con.close()


if __name__ == "__main__":
    assert mask_sensitive_value("1234 5678 9012") == "XXXX-XXXX-9012"
    assert sanitize_aadhaar("1234-5678-901")[1] == "E002_INVALID_AADHAAR_FORMAT"
    assert normalize_credit_score(950)[0] == 900 and compute_risk_index(10000, "poor") == 80.0
    run_pipeline()