import re

def mask_aadhaar(aadhaar_str):
    if not aadhaar_str:
        return None
    digits = re.sub(r'\D', '', str(aadhaar_str))
    if len(digits) != 12:
        return None
    return f"XXXX-XXXX-{digits[-4:]}"

def calculate_risk_index(income, credit_score):
    try:
        inc = float(income) if income is not None else 0.0
        score = float(credit_score) if credit_score is not None else 0.0
    except (ValueError, TypeError):
        return 1.0
    if inc <= 0:
        return 1.0
    norm_score = max(0.0, min(1.0, (score - 300.0) / 550.0))
    norm_inc = max(0.0, min(1.0, inc / 100000.0))
    risk = 1.0 - (0.6 * norm_score + 0.4 * norm_inc)
    return round(max(0.0, min(1.0, risk)), 4)

def transform_batch(raw_records: list) -> list:
    if not raw_records:
        return []
    cleansed = []
    for record in raw_records:
        if not isinstance(record, dict):
            continue
        clean_record = {}
        for k, v in record.items():
            k_clean = k.strip() if isinstance(k, str) else k
            v_clean = v.strip() if isinstance(v, str) else v
            clean_record[k_clean] = v_clean
        raw_aadhaar = clean_record.get('aadhaar_no') or clean_record.get('aadhaar')
        clean_record['aadhaar_masked'] = mask_aadhaar(raw_aadhaar)
        income = clean_record.get('monthly_income') or clean_record.get('income')
        credit_score = clean_record.get('credit_score') or clean_record.get('credit_history')
        clean_record['risk_index'] = calculate_risk_index(income, credit_score)
        cleansed.append(clean_record)
    return cleansed