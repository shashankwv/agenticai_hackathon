import json
import re
import duckdb
import pandas as pd
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "etl.duckdb"
MOBILE_LEN = 10
FIELD_MAP = {"alt_phone": "alternate_contact_number", "secondary_phone": "alternate_contact_number", "phone": "primary_contact_number", "mobile": "primary_contact_number"}
TARGET_COLS = ["id", "customer_name", "email", "primary_contact_number", "alternate_contact_number", "channel", "changed_by", "processed_at"]
DQ_EXCEPTIONS: list[dict] = []
AUDIT_RECORDS: list[dict] = []


def mask_sensitive_value(val: str, keep_last: int = 4) -> str:
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    s = str(val)
    if len(s) <= keep_last:
        return "*" * len(s)
    return "*" * (len(s) - keep_last) + s[-keep_last:]


def normalize_number(val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return re.sub(r"\D", "", str(val)) or None


def log_dq(rid, field, value, rule):
    DQ_EXCEPTIONS.append({"id": rid, "field": field, "value": mask_sensitive_value(value), "rule": rule, "logged_at": pd.Timestamp.utcnow()})


def transform_batch(raw_records: list[dict]) -> list[dict]:
    out = []
    for rec in raw_records:
        row = {FIELD_MAP.get(k, k): v for k, v in rec.items()}
        rid = row.get("id")
        primary = normalize_number(row.get("primary_contact_number"))
        raw_alt = row.get("alternate_contact_number")
        alt = normalize_number(raw_alt)
        if alt is not None and len(alt) != MOBILE_LEN:
            log_dq(rid, "alternate_contact_number", raw_alt, "invalid_mobile_length")
            alt = None
        if alt is not None and alt == primary:
            log_dq(rid, "alternate_contact_number", raw_alt, "equals_primary_contact_number")
            alt = None
        old_alt = row.pop("_prev_alternate", None)
        if (old_alt or None) != (alt or None):
            AUDIT_RECORDS.append({"id": rid, "field": "alternate_contact_number", "old_value": mask_sensitive_value(old_alt), "new_value": mask_sensitive_value(alt), "changed_by": row.get("changed_by", "etl_pipeline"), "channel": row.get("channel", "unknown"), "changed_at": pd.Timestamp.utcnow()})
        clean = {c: row.get(c) for c in TARGET_COLS}
        clean["primary_contact_number"] = mask_sensitive_value(primary)
        clean["alternate_contact_number"] = mask_sensitive_value(alt)
        clean["email"] = mask_sensitive_value(row.get("email"), 6)
        clean["processed_at"] = pd.Timestamp.utcnow()
        out.append(clean)
    return out


def parse_payload(p):
    if p is None:
        return {}
    return json.loads(p) if isinstance(p, str) else dict(p)


def run_pipeline():
    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE TABLE IF NOT EXISTS landing_ui (id VARCHAR, ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, payload JSON);")
    con.execute("CREATE TABLE IF NOT EXISTS staging_ui (id VARCHAR, customer_name VARCHAR, email VARCHAR, primary_contact_number VARCHAR, alternate_contact_number VARCHAR, channel VARCHAR, changed_by VARCHAR, processed_at TIMESTAMP);")
    con.execute("CREATE TABLE IF NOT EXISTS audit_log (id VARCHAR, field VARCHAR, old_value VARCHAR, new_value VARCHAR, changed_by VARCHAR, channel VARCHAR, changed_at TIMESTAMP);")
    con.execute("CREATE TABLE IF NOT EXISTS dq_exceptions (id VARCHAR, field VARCHAR, value VARCHAR, rule VARCHAR, logged_at TIMESTAMP);")
    con.execute("UPDATE staging_ui SET alternate_contact_number = NULL WHERE alternate_contact_number = '';")
    landing = con.execute("SELECT id, CAST(payload AS VARCHAR) AS payload FROM landing_ui ORDER BY ingested_at;").fetchdf()
    prev = dict(con.execute("SELECT id, alternate_contact_number FROM staging_ui;").fetchall())
    raw_records = []
    for _, r in landing.iterrows():
        rec = parse_payload(r["payload"])
        rec.setdefault("id", r["id"])
        rec["_prev_alternate"] = prev.get(rec["id"])
        raw_records.append(rec)
    transformed = transform_batch(raw_records)
    if transformed:
        df = pd.DataFrame(transformed, columns=TARGET_COLS)
        con.register("staging_df", df)
        con.execute("DELETE FROM staging_ui WHERE id IN (SELECT id FROM staging_df);")
        con.execute("INSERT INTO staging_ui SELECT * FROM staging_df;")
    if AUDIT_RECORDS:
        con.register("audit_df", pd.DataFrame(AUDIT_RECORDS))
        con.execute("INSERT INTO audit_log SELECT * FROM audit_df;")
    if DQ_EXCEPTIONS:
        con.register("dq_df", pd.DataFrame(DQ_EXCEPTIONS))
        con.execute("INSERT INTO dq_exceptions SELECT * FROM dq_df;")
    total = con.execute("SELECT COUNT(*) FROM staging_ui;").fetchone()[0]
    con.close()
    print(f"landing_rows={len(landing)} transformed={len(transformed)} audit_records={len(AUDIT_RECORDS)} dq_exceptions={len(DQ_EXCEPTIONS)} staging_total={total}")


if __name__ == "__main__":
    run_pipeline()