import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import duckdb

DB_PATH = Path(__file__).resolve().parent / 'staging.duckdb'
TABLE_NAME = 'cleansed_staging_data'

TABLE_SCHEMA = [
    ('additionalProp1', 'MAP(INTEGER, INTEGER)'),
    ('risk_index', 'DOUBLE'),
    ('full_name', 'VARCHAR'),
    ('dob', 'VARCHAR'),
    ('email', 'VARCHAR'),
    ('phone', 'VARCHAR'),
    ('aadhaar_no', 'VARCHAR'),
    ('address_line1', 'VARCHAR'),
    ('address_line2', 'VARCHAR'),
    ('city', 'VARCHAR'),
    ('state', 'VARCHAR'),
    ('pincode', 'VARCHAR'),
    ('employment_type', 'VARCHAR'),
    ('annual_income', 'VARCHAR'),
    ('credit_score', 'DOUBLE'),
    ('terms_accepted', 'BOOLEAN'),
    ('pan_no', 'VARCHAR'),
    ('nominee_name', 'VARCHAR'),
    ('relationship', 'VARCHAR'),
    ('aadhaar_masked', 'VARCHAR'),
    ('alternate_phone', 'VARCHAR'),
    ('a_brand_new_field_from_agent03', 'DOUBLE'),
    ('masked_aadhaar', 'VARCHAR'),
    ('loyalty_points', 'DOUBLE'),
]
OUTPUT_FIELDS = [col for col, _ in TABLE_SCHEMA]


# ---------------------------------------------------------------------------
# Generic sanitisation helpers
# ---------------------------------------------------------------------------

def _clean_str(val: Any) -> Optional[str]:
    if val is None or isinstance(val, (dict, list, tuple, set)):
        return None
    text = str(val).strip()
    text = re.sub(r'\s+', ' ', text)
    return text if text else None


def _to_float(val: Any) -> Optional[float]:
    if val is None or isinstance(val, bool):
        return None
    if isinstance(val, (int, float)):
        return float(val)
    text = _clean_str(val)
    if text is None:
        return None
    text = re.sub(r'[^0-9.\-]', '', text.replace(',', ''))
    if text in ('', '-', '.', '-.'):
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _to_bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    if isinstance(val, (int, float)):
        return val != 0
    text = str(val).strip().lower()
    return text in ('true', '1', 'yes', 'y', 't', 'on', 'accepted')


def _digits(val: Any) -> Optional[str]:
    text = _clean_str(val)
    if text is None:
        return None
    digits = re.sub(r'\D', '', text)
    return digits if digits else None


def _clean_phone(val: Any) -> Optional[str]:
    digits = _digits(val)
    if digits is None:
        return None
    if len(digits) > 10:
        digits = digits[-10:]
    return digits


def _clean_email(val: Any) -> Optional[str]:
    text = _clean_str(val)
    if text is None:
        return None
    return text.replace(' ', '').lower()


def _clean_pan(val: Any) -> Optional[str]:
    text = _clean_str(val)
    if text is None:
        return None
    cleaned = re.sub(r'[^A-Z0-9]', '', text.upper())
    return cleaned if cleaned else None


def _clean_pincode(val: Any) -> Optional[str]:
    digits = _digits(val)
    if digits is None:
        return None
    return digits[:6]


def _clean_dob(val: Any) -> Optional[str]:
    text = _clean_str(val)
    if text is None:
        return None
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y', '%Y/%m/%d', '%d.%m.%Y', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M:%S'):
        try:
            return datetime.strptime(text, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return text


def _clean_title(val: Any) -> Optional[str]:
    text = _clean_str(val)
    if text is None:
        return None
    return text.title()


def _clean_income(val: Any) -> Optional[str]:
    amount = _to_float(val)
    if amount is None:
        return None
    return '%.2f' % abs(amount)


def _clean_credit_score(val: Any) -> Optional[float]:
    score = _to_float(val)
    if score is None:
        return None
    if score < 0 or score > 1000:
        return None
    return float(min(max(score, 300.0), 900.0))


def _to_int_map(val: Any) -> Dict[int, int]:
    result: Dict[int, int] = {}
    if not isinstance(val, dict):
        return result
    for key, value in val.items():
        try:
            result[int(str(key).strip())] = int(float(str(value).strip()))
        except (ValueError, TypeError):
            continue
    return result


# ---------------------------------------------------------------------------
# Domain logic
# ---------------------------------------------------------------------------

def mask_aadhaar(aadhaar_str: Any) -> Optional[str]:
    if aadhaar_str is None:
        return None
    digits = re.sub(r'\D', '', str(aadhaar_str))
    if len(digits) < 4:
        return None
    return 'XXXX-XXXX-' + digits[-4:]


def calculate_risk_index(credit_score: Optional[float], annual_income: Optional[float]) -> float:
    if credit_score is None and annual_income is None:
        return 50.0
    if credit_score is not None:
        bounded = min(max(credit_score, 300.0), 900.0)
        risk = (900.0 - bounded) / 6.0
    else:
        risk = 60.0
    if annual_income is not None:
        if annual_income < 300000:
            risk += 10.0
        elif annual_income < 600000:
            risk += 5.0
        elif annual_income >= 1500000:
            risk -= 10.0
        elif annual_income >= 1000000:
            risk -= 5.0
    risk = min(max(risk, 0.0), 100.0)
    return round(float(risk), 2)


def transform_record(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}
    credit_score = _clean_credit_score(raw.get('credit_score'))
    income_str = _clean_income(raw.get('annual_income'))
    income_val = float(income_str) if income_str is not None else None
    masked = mask_aadhaar(raw.get('aadhaar_no'))
    loyalty = _to_float(raw.get('loyalty_points'))

    record: Dict[str, Any] = {
        'additionalProp1': _to_int_map(raw.get('additionalProp1')),
        'risk_index': calculate_risk_index(credit_score, income_val),
        'full_name': _clean_title(raw.get('full_name')),
        'dob': _clean_dob(raw.get('dob')),
        'email': _clean_email(raw.get('email')),
        'phone': _clean_phone(raw.get('phone')),
        'aadhaar_no': masked,
        'address_line1': _clean_str(raw.get('address_line1')),
        'address_line2': _clean_str(raw.get('address_line2')),
        'city': _clean_title(raw.get('city')),
        'state': _clean_title(raw.get('state')),
        'pincode': _clean_pincode(raw.get('pincode')),
        'employment_type': _clean_title(raw.get('employment_type')),
        'annual_income': income_str,
        'credit_score': credit_score,
        'terms_accepted': _to_bool(raw.get('terms_accepted')),
        'pan_no': _clean_pan(raw.get('pan_no')),
        'nominee_name': _clean_title(raw.get('nominee_name')),
        'relationship': _clean_title(raw.get('relationship')),
        'aadhaar_masked': masked,
        'alternate_phone': _clean_phone(raw.get('alternate_phone')),
        'a_brand_new_field_from_agent03': _to_float(raw.get('a_brand_new_field_from_agent03')),
        'masked_aadhaar': masked,
        'loyalty_points': loyalty if loyalty is not None else 0.0,
    }
    for field in OUTPUT_FIELDS:
        record.setdefault(field, None)
    return record


def transform_batch(raw_records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not raw_records:
        return []
    return [transform_record(rec) for rec in raw_records]


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def _ensure_table(con: duckdb.DuckDBPyConnection) -> None:
    cols = ', '.join('%s %s' % (col, dtype) for col, dtype in TABLE_SCHEMA)
    con.execute('CREATE TABLE IF NOT EXISTS %s (%s)' % (TABLE_NAME, cols))


def _existing_columns(con: duckdb.DuckDBPyConnection) -> Dict[str, str]:
    rows = con.execute(
        'SELECT column_name, data_type FROM information_schema.columns WHERE lower(table_name) = ?',
        [TABLE_NAME.lower()],
    ).fetchall()