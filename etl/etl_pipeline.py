import json
import re
import duckdb
import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "etl.duckdb"
CONFIG_PATH = BASE_DIR / "risk_config.json"
DEFAULT_CONFIG = {"income_weight": 0.4, "credit_weight": 0.6, "income_cap": 200000.0, "credit_min": 300, "credit_max": 900, "scale": 100}
AADHAAR_RE = re.compile(r"^\d{12}$")
STAGING_COLS = ["id", "aadhaar_no", "aadhaar_masked", "monthly_income", "credit_history", "credit_score", "risk_index", "status", "reject_reason"]


def load_config() -> dict:
    if CONFIG_PATH.exists():
        return {**DEFAULT_CONFIG, **json.loads(CONFIG_PATH.read_text())}
    return dict(DEFAULT_CONFIG)


def mask_sensitive_value(val: str, keep_last: int = 4) -> str:
    digits = re.sub(r"\D", "", str(val or ""))
    tail = digits[-keep_last:] if keep_last > 0 else ""
    return f"XXXX-XXXX-{tail.rjust(max(keep_last, 0), 'X')}"


def sanitize_aadhaar(val) -> str | None:
    cleaned = re.sub(r"\D", "", str(val if val is not None else "").strip())
    return cleaned if AADHAAR_RE.match(cleaned) else None


def _to_float(val) -> float | None:
    try:
        return float(val) if val not in (None, "") else None
    except (TypeError, ValueError):
        return None


def compute_risk_index(monthly_income, credit_history, config: dict) -> float:
    income_norm = min(max(float(monthly_income or 0.0), 0.0), config["income_cap"]) / config["income_cap"]
    span = float(config["credit_max"] - config["credit_min"])
    credit_val = min(max(float(credit_history if credit_history is not None else config["credit_min"]), config["credit_min"]), config["credit_max"])
    credit_norm = (credit_val - config["credit_min"]) / span
    risk = 1.0 - (config["income_weight"] * income_norm + config["credit_weight"] * credit_norm)
    return round(max(0.0, min(1.0, risk)) * config["scale"], 2)


def risk_to_credit_score(risk_index: float, config: dict) -> int:
    span = config["credit_max"] - config["credit_min"]
    return int(round(config["credit_max"] - (risk_index / config["scale"]) * span))


def transform_batch(raw_records: list[dict], config: dict | None = None) -> list[dict]:
    config = config or load_config()
    out = []
    for rec in raw_records:
        payload = rec.get("payload", rec)
        payload = json.loads(payload) if isinstance(payload, str) else (payload or {})
        aadhaar = sanitize_aadhaar(payload.get("aadhaar_no"))
        row = {"id": str(rec.get("id") or payload.get("id") or ""), "aadhaar_no": aadhaar, "aadhaar_masked": mask_sensitive_value(payload.get("aadhaar_no")),
               "monthly_income": _to_float(payload.get("monthly_income")), "credit_history": _to_float(payload.get("credit_history"))}
        if aadhaar is None:
            row.update({"credit_score": None, "risk_index": None, "status": "rejected", "reject_reason": "invalid_aadhaar"})
        else:
            risk = compute_risk_index(row["monthly_income"], row["credit_history"], config)
            row.update({"credit_score": risk_to_credit_score(risk, config), "risk_index": risk, "status": "valid", "reject_reason": None})
        out.append(row)
    return out


def run_pipeline() -> None:
    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE TABLE IF NOT EXISTS landing_ui (id VARCHAR, ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, payload JSON);")
    schema = "(id VARCHAR, aadhaar_no VARCHAR, aadhaar_masked VARCHAR, monthly_income DOUBLE, credit_history DOUBLE, credit_score INTEGER, risk_index DOUBLE, status VARCHAR, reject_reason VARCHAR)"
    con.execute(f"CREATE TABLE IF NOT EXISTS staging_ui {schema};")
    con.execute(f"CREATE TABLE IF NOT EXISTS quarantine_ui {schema};")
    raw = [{"id": r[0], "payload": r[1]} for r in con.execute("SELECT id, payload FROM landing_ui").fetchall()]
    rows = transform_batch(raw)
    df = pd.DataFrame(rows, columns=STAGING_COLS)
    valid = df[df["status"] == "valid"]
    rejected = df[df["status"] != "valid"]
    placeholders = ", ".join(["?"] * len(STAGING_COLS))
    if not valid.empty:
        con.executemany(f"INSERT INTO staging_ui VALUES ({placeholders})", valid.astype(object).where(valid.notna(), None).values.tolist())
    if not rejected.empty:
        con.executemany(f"INSERT INTO quarantine_ui VALUES ({placeholders})", rejected.astype(object).where(rejected.notna(), None).values.tolist())
    for _, r in rejected.iterrows():
        print(f"[QUARANTINE] id={r['id']} aadhaar={r['aadhaar_masked']} reason={r['reject_reason']}")
    print(f"landing={len(raw)} staged={len(valid)} quarantined={len(rejected)} db={DB_PATH.name}")
    con.close()


if __name__ == "__main__":
    run_pipeline()