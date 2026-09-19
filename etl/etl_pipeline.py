import json
import re
import duckdb
import pandas as pd
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "etl.duckdb"
AADHAAR_RE = re.compile(r"^\d{12}$")
STAGING_COLS = ["id", "aadhaar_masked", "monthly_income", "credit_history", "credit_score", "risk_index", "status"]


def mask_sensitive_value(val: str, keep_last: int = 4) -> str:
    s = "" if val is None else str(val)
    if not s:
        return ""
    tail = s[-keep_last:] if keep_last > 0 else ""
    hidden = "X" * max(len(s) - len(tail), 0)
    full = hidden + tail
    groups = [full[i:i + 4] for i in range(0, len(full), 4)]
    return "-".join(groups)


def sanitize_aadhaar(raw) -> str | None:
    if raw is None:
        return None
    cleaned = re.sub(r"[\s\-]", "", str(raw))
    return cleaned if AADHAAR_RE.match(cleaned) else None


def compute_risk_index(monthly_income, credit_history) -> int:
    try:
        income = float(monthly_income or 0)
    except (TypeError, ValueError):
        income = 0.0
    score = 50
    if income >= 100000:
        score -= 20
    elif income >= 50000:
        score -= 10
    elif income < 20000:
        score += 15
    history = str(credit_history or "none").strip().lower()
    score += {"excellent": -25, "good": -15, "fair": 0, "poor": 25, "none": 10}.get(history, 10)
    return max(0, min(100, score))


def transform_batch(raw_records: list[dict]) -> list[dict]:
    out = []
    for rec in raw_records:
        payload = rec.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        aadhaar = sanitize_aadhaar(payload.get("aadhaar_no"))
        income = payload.get("monthly_income")
        history = payload.get("credit_history")
        try:
            credit_score = int(payload.get("credit_score")) if payload.get("credit_score") is not None else None
        except (TypeError, ValueError):
            credit_score = None
        row = {
            "id": str(rec.get("id") or payload.get("id") or ""),
            "aadhaar_masked": mask_sensitive_value(aadhaar) if aadhaar else None,
            "monthly_income": float(income) if isinstance(income, (int, float)) else None,
            "credit_history": str(history) if history is not None else None,
            "credit_score": credit_score,
            "risk_index": compute_risk_index(income, history),
            "status": "ok" if aadhaar else "quarantined",
        }
        out.append(row)
    return out


def run_pipeline():
    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE TABLE IF NOT EXISTS landing_ui (id VARCHAR, ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, payload JSON);")
    con.execute("CREATE TABLE IF NOT EXISTS staging_ui (id VARCHAR, aadhaar_masked VARCHAR, monthly_income DOUBLE, credit_history VARCHAR, credit_score INTEGER, risk_index INTEGER, status VARCHAR, processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")
    raw_df = con.execute("SELECT id, CAST(payload AS VARCHAR) AS payload FROM landing_ui ORDER BY ingested_at").df()
    raw_records = raw_df.to_dict(orient="records")
    transformed = transform_batch(raw_records)
    staged_df = pd.DataFrame(transformed, columns=STAGING_COLS)
    if not staged_df.empty:
        con.register("staged_df", staged_df)
        con.execute("INSERT INTO staging_ui (id, aadhaar_masked, monthly_income, credit_history, credit_score, risk_index, status) SELECT id, aadhaar_masked, monthly_income, credit_history, credit_score, risk_index, status FROM staged_df")
        con.unregister("staged_df")
    total = len(transformed)
    quarantined = sum(1 for r in transformed if r["status"] == "quarantined")
    print(f"landing_ui rows read: {total}")
    print(f"staging_ui rows loaded: {total} (ok={total - quarantined}, quarantined={quarantined})")
    for r in transformed[:5]:
        print(f"id={r['id']} aadhaar={r['aadhaar_masked']} credit_score={r['credit_score']} risk_index={r['risk_index']} status={r['status']}")
    con.close()


if __name__ == "__main__":
    run_pipeline()