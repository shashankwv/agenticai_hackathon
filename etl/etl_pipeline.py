import json, uuid, re, duckdb, logging, sys
import pandas as pd
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s", stream=sys.stdout)
log = logging.getLogger("etl_intake")
DB_PATH = Path(__file__).resolve().parent / "etl.duckdb"
SENSITIVE_PATTERN = re.compile(r"ssn|tax_id|secret|password|token", re.I)
MARITAL_ALLOWED = {"single", "married", "divorced", "widowed"}
MARITAL_REASON = "EXPECTED_ONE_OF_Single|Married|Divorced|Widowed"
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

# (field-name regex, validator, reason code) - applied dynamically to any payload key matching the pattern
FIELD_RULES = [
    (r"^_malformed", lambda v: False, "INVALID_JSON_PAYLOAD_EXPECTED_OBJECT"),
    (r"marital", lambda v: v.lower() in MARITAL_ALLOWED, "INVALID_MARITAL_STATUS_" + MARITAL_REASON),
    (r"ssn|tax_id", lambda v: "*" in v or re.fullmatch(r"\d{9}", v) is not None, "INVALID_SSN_EXPECTED_9_DIGITS_OR_MASKED_FORMAT"),
    (r"phone", lambda v: re.fullmatch(r"\d{10,15}", v) is not None, "INVALID_PHONE_EXPECTED_10_TO_15_DIGITS"),
    (r"email", lambda v: re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", v) is not None, "INVALID_EMAIL_EXPECTED_USER@DOMAIN.TLD"),
    (r"name", lambda v: len(v) > 0, "INVALID_NAME_EXPECTED_NON_EMPTY_STRING"),
]
NOT_NULL_PATTERN = re.compile(r"marital", re.I)  # present-but-null values for these keys are quarantined


def mask_sensitive_value(val: str, keep_last: int = 4) -> str:
    if val is None:
        return None
    s = str(val)
    if "*" in s:
        return s
    tail = s[-keep_last:] if keep_last > 0 else ""
    return "*" * max(len(s) - len(tail), 0) + tail


def normalize_value(key: str, val):
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    if isinstance(val, (dict, list)):
        return json.dumps(val)
    s = str(val).strip()
    if not s or s.lower() in ("null", "none", "nan"):
        return None
    k = key.lower()
    if re.search(r"phone|ssn|tax_id", k) and "*" not in s:
        s = re.sub(r"\D", "", s)
    elif "email" in k:
        s = s.lower()
    elif "marital" in k:
        s = s.title()
    return s


def transform_batch(raw_records: list[dict]) -> tuple[list[dict], list[dict]]:
    valid, rejected, seen_ids = [], [], set()
    for idx, raw in enumerate(raw_records):
        rec, errors = {}, []
        for key, val in (raw or {}).items():
            k = str(key).strip()
            if not k:
                continue
            v = normalize_value(k, val)
            if v is None:
                if NOT_NULL_PATTERN.search(k):
                    errors.append(f"{k}:NULL_MARITAL_STATUS_{MARITAL_REASON}")
                rec[k] = None
                continue
            for pattern, check, reason in FIELD_RULES:
                if re.search(pattern, k, re.I):
                    if not check(v):
                        errors.append(f"{k}:{reason}")
                    break
            rec[k] = mask_sensitive_value(v) if SENSITIVE_PATTERN.search(k) else v
        rid = rec.get("id")
        if not rid or not UUID_RE.match(str(rid)) or rid in seen_ids:
            rec["id"] = str(uuid.uuid4())
            log.info("Record #%d: missing/invalid/duplicate id %r -> assigned %s", idx, rid, rec["id"])
        seen_ids.add(rec["id"])
        if errors:
            log.warning("Record %s quarantined: %s", rec["id"], "; ".join(errors))
            rejected.append({"id": rec["id"], "reasons": errors, "record": rec})
        else:
            valid.append(rec)
    log.info("transform_batch: %d valid, %d rejected", len(valid), len(rejected))
    return valid, rejected


def run_pipeline():
    log.info("Connecting to DuckDB at %s", DB_PATH)
    con = duckdb.connect(str(DB_PATH))
    con.execute("CREATE TABLE IF NOT EXISTS landing_ui (id VARCHAR PRIMARY KEY DEFAULT gen_random_uuid(), ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, payload JSON);")
    con.execute("CREATE TABLE IF NOT EXISTS staging_ui (id VARCHAR PRIMARY KEY, staged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")
    con.execute("CREATE TABLE IF NOT EXISTS error_ui (id VARCHAR, reason VARCHAR, payload JSON, logged_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);")
    df = con.execute("SELECT id, payload FROM landing_ui").df()
    log.info("Read %d landing rows", len(df))
    raw_records = []
    for lid, payload in zip(df["id"], df["payload"]):
        try:
            p = json.loads(payload) if isinstance(payload, str) else (payload or {})
            if not isinstance(p, dict):
                raise ValueError("payload is not a JSON object")
        except (ValueError, TypeError) as exc:
            log.error("Landing %s: malformed payload (%s)", lid, exc)
            p = {"_malformed_payload": str(payload)}
        p.setdefault("id", lid)
        raw_records.append(p)
    valid_records, rejected_records = transform_batch(raw_records)
    all_keys = sorted(list(set(k for r in valid_records for k in r.keys() if k not in ("id", "staged_at"))))
    existing = {row[1] for row in con.execute("PRAGMA table_info('staging_ui')").fetchall()}
    for key in all_keys:
        if key not in existing:
            log.info("Schema evolution: ALTER TABLE staging_ui ADD COLUMN \"%s\" VARCHAR (existing rows backfilled NULL)", key)
            con.execute('ALTER TABLE staging_ui ADD COLUMN "' + key + '" VARCHAR')
    if valid_records:
        cols = ["id"] + all_keys
        quoted_cols = ['"' + c + '"' for c in cols]
        placeholders = ["?"] * len(cols)
        update_set = ['"' + k + '"=EXCLUDED."' + k + '"' for k in all_keys]
        if update_set:
            sql = "INSERT INTO staging_ui (" + ", ".join(quoted_cols) + ") VALUES (" + ", ".join(placeholders) + ") ON CONFLICT (id) DO UPDATE SET " + ", ".join(update_set)
        else:
            sql = "INSERT INTO staging_ui (id) VALUES (?) ON CONFLICT (id) DO NOTHING"
        params = [[r.get("id")] + [r.get(k) for k in all_keys] for r in valid_records]
        con.executemany(sql, params)
        log.info("Upserted %d rows into staging_ui across %d dynamic columns", len(params), len(all_keys))
    if rejected_records:
        con.executemany("INSERT INTO error_ui (id, reason, payload) VALUES (?, ?, ?)",
                        [[r["id"], "; ".join(r["reasons"]), json.dumps(r["record"], default=str)] for r in rejected_records])
        log.info("Logged %d rejected records to error_ui", len(rejected_records))
    con.close()
    summary = {"landing": len(raw_records), "loaded": len(valid_records), "rejected": len(rejected_records), "rejected_records": rejected_records}
    print(json.dumps(summary, indent=2, default=str))


if __name__ == "__main__":
    run_pipeline()