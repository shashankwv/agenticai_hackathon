import json
import duckdb
import pandas as pd
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "etl.duckdb"
ALLOWED_MARITAL = {"Single", "Married", "Divorced", "Widowed"}
SENSITIVE_FIELDS = ("email", "phone", "national_id", "account_number")
STAGING_COLUMNS = ["id", "ingested_at", "full_name", "email", "phone", "national_id", "account_number", "marital_status", "is_valid", "rejection_reason"]
CREATE_LANDING = "CREATE TABLE IF NOT EXISTS landing_ui (id VARCHAR, ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, payload JSON);"
CREATE_STAGING = "CREATE TABLE IF NOT EXISTS staging_ui (id VARCHAR, ingested_at TIMESTAMP, full_name VARCHAR, email VARCHAR, phone VARCHAR, national_id VARCHAR, account_number VARCHAR, marital_status VARCHAR, is_valid BOOLEAN, rejection_reason VARCHAR);"


def mask_sensitive_value(val: str, keep_last: int = 4) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val)
    if len(s) <= keep_last:
        return "*" * len(s)
    return "*" * (len(s) - keep_last) + s[-keep_last:]


def validate_marital_status(value):
    if value is None or (isinstance(value, float) and pd.isna(value)) or str(value).strip() == "":
        return None, False, "marital_status is null (KYC mandatory)"
    cleaned = str(value).strip().capitalize()
    if cleaned not in ALLOWED_MARITAL:
        return str(value), False, f"marital_status invalid: {value}"
    return cleaned, True, None


def transform_batch(raw_records: list[dict]) -> list[dict]:
    out = []
    for rec in raw_records:
        payload = rec.get("payload") or {}
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except json.JSONDecodeError:
                payload = {}
        row = {"id": rec.get("id"), "ingested_at": rec.get("ingested_at")}
        row["full_name"] = (str(payload.get("full_name") or "").strip()) or None
        for field in SENSITIVE_FIELDS:
            row[field] = mask_sensitive_value(payload.get(field))
        marital, ok, reason = validate_marital_status(payload.get("marital_status"))
        row["marital_status"] = marital
        row["is_valid"] = ok
        row["rejection_reason"] = reason
        out.append(row)
    return out


def run_pipeline():
    con = duckdb.connect(str(DB_PATH))
    con.execute(CREATE_LANDING)
    con.execute(CREATE_STAGING)
    landing_df = con.execute("SELECT id, ingested_at, CAST(payload AS VARCHAR) AS payload FROM landing_ui").df()
    raw_records = landing_df.to_dict(orient="records")
    transformed = transform_batch(raw_records)
    staging_df = pd.DataFrame(transformed, columns=STAGING_COLUMNS)
    staging_df["ingested_at"] = pd.to_datetime(staging_df["ingested_at"])
    staging_df["is_valid"] = staging_df["is_valid"].astype(bool)
    con.register("staging_df", staging_df)
    con.execute("DELETE FROM staging_ui")
    con.execute("INSERT INTO staging_ui SELECT * FROM staging_df")
    con.unregister("staging_df")
    total = len(staging_df)
    valid = int(staging_df["is_valid"].sum()) if total else 0
    staged = con.execute("SELECT COUNT(*) FROM staging_ui").fetchone()[0]
    con.close()
    print(f"landing_ui rows: {total} | valid: {valid} | flagged: {total - valid} | staging_ui rows: {staged}")


def run_tests():
    cases = [({"marital_status": "Married"}, True), ({"marital_status": "single"}, True), ({"marital_status": None}, False), ({"marital_status": "Complicated"}, False), ({}, False)]
    for payload, expected in cases:
        result = transform_batch([{"id": "t", "payload": json.dumps(payload)}])[0]
        assert result["is_valid"] is expected, result
    assert transform_batch([{"id": "b", "payload": "{}"}])[0]["marital_status"] is None
    assert mask_sensitive_value("123456789") == "*****6789"
    assert mask_sensitive_value("12") == "**"
    print("tests passed")


if __name__ == "__main__":
    run_tests()
    run_pipeline()