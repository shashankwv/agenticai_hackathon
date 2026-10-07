import json, uuid, re, duckdb
import pandas as pd
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "etl.duckdb"
ALLOWED_MARITAL = {"Single", "Married", "Divorced", "Widowed"}
PLACEHOLDERS = {"", "null", "none", "n/a", "na", "tbd", "todo", "placeholder", "uuid", "<id>", "0"}
SENSITIVE_KEY_RE = re.compile(r"(_no|ssn|pan|aadhaar|id_number)$", re.IGNORECASE)
DOMAIN_RULES = {
    "ssn": (r"\d{9}", "XXX-XX-XXXX", False),
    "aadhaar": (r"\d{12}", "XXXX XXXX XXXX", False),
    "pan": (r"[A-Z]{5}\d{4}[A-Z]", "AAAAA9999A", True),
    "id_number": (r"[A-Z0-9]{6,20}", "A1B2C3D4E5", True),
    "_no": (r"\d{6,20}", "123456789", False),
}
UUID_RE = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def mask_sensitive_value(val: str, keep_last: int = 4) -> str:
    s = "" if val is None else str(val)
    if len(s) <= keep_last:
        return "*" * len(s)
    return "*" * (len(s) - keep_last) + s[-keep_last:]


def _domain_for(key: str) -> str:
    k = key.lower()
    for dom in ("ssn", "aadhaar", "pan", "id_number"):
        if k.endswith(dom):
            return dom
    return "_no"


def _clean_identifier(val, alnum: bool) -> str:
    s = "" if val is None else str(val).upper()
    return re.sub(r"[^A-Z0-9]", "", s) if alnum else re.sub(r"\D", "", s)


def _is_placeholder(val) -> bool:
    return val is None or str(val).strip().lower() in PLACEHOLDERS


def _reject(rec_id, key, reason_key, sample, masked=None):
    return {"record_id": rec_id, "field": key, "reason_key": reason_key, "value_masked": masked, "expected_sample": sample}


def transform_batch(raw_records: list[dict]) -> tuple[list[dict], list[dict]]:
    valid, rejected = [], []
    for raw in raw_records:
        rec = dict(raw or {})
        rec_id = rec.get("id") or rec.get("customer_id")
        if _is_placeholder(rec_id) or not UUID_RE.fullmatch(str(rec_id).strip()):
            rec_id = str(uuid.uuid4())
        rec["id"] = rec_id
        reason = None
        for key in [k for k in rec if SENSITIVE_KEY_RE.search(k)]:
            pattern, sample, alnum = DOMAIN_RULES[_domain_for(key)]
            cleaned = _clean_identifier(rec[key], alnum)
            if not re.fullmatch(pattern, cleaned):
                reason = _reject(rec_id, key, f"invalid_{key.lower()}_format", sample, mask_sensitive_value(cleaned))
                break
            rec[key] = cleaned
        if reason is None:
            ms = rec.get("marital_status")
            historical = str(rec.get("source", "")).lower() == "historical"
            if ms is None or (isinstance(ms, float) and pd.isna(ms)) or str(ms).strip() == "":
                rec["marital_status"] = None
                if not historical:
                    reason = _reject(rec_id, "marital_status", "marital_status_null", "Single|Married|Divorced|Widowed")
            else:
                norm = str(ms).strip().capitalize()
                if norm in ALLOWED_MARITAL:
                    rec["marital_status"] = norm
                else:
                    reason = _reject(rec_id, "marital_status", "marital_status_unknown", "Single|Married|Divorced|Widowed", str(ms))
        (rejected if reason else valid).append(reason or rec)
    return valid, rejected


def run_pipeline():
    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE TABLE IF NOT EXISTS landing_ui (id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid(), ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, payload JSON);")
    con.execute("CREATE TABLE IF NOT EXISTS staging_ui (id VARCHAR PRIMARY KEY, marital_status VARCHAR, payload JSON, loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")
    rows = con.execute("SELECT id, CAST(payload AS VARCHAR) FROM landing_ui").fetchall()
    raw_records = []
    for landing_id, payload in rows:
        try:
            body = json.loads(payload) if payload else {}
        except (TypeError, ValueError):
            body = {}
        body = body if isinstance(body, dict) else {"payload": body}
        body.setdefault("id", landing_id)
        raw_records.append(body)
    valid, rejected = transform_batch(raw_records)
    if valid:
        df = pd.DataFrame({"id": [r["id"] for r in valid], "marital_status": [r.get("marital_status") for r in valid], "payload": [json.dumps(r, default=str) for r in valid]})
        con.register("df_valid", df)
        con.execute("INSERT OR REPLACE INTO staging_ui SELECT id, marital_status, CAST(payload AS JSON), CURRENT_TIMESTAMP FROM df_valid")
    con.close()
    summary = {"landing": len(rows), "loaded": len(valid), "rejected": len(rejected)}
    print("EXECUTION SUMMARY:", json.dumps(summary))
    for r in rejected:
        print(f"REJECTED record_id={r['record_id']} field={r['field']} reason_key={r['reason_key']} value={r['value_masked']} expected_sample=\"{r['expected_sample']}\"")
    return summary


if __name__ == "__main__":
    run_pipeline()