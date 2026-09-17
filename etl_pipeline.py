import duckdb
from pathlib import Path
from typing import List, Dict, Any

# Resolve DuckDB path relative to project root
DUCKDB_PATH = Path(__file__).resolve().parent / 'staging.duckdb'

def mask_aadhaar(val: str) -> str:
    """
    Mask Aadhaar number by keeping only the last 4 digits.
    
    Args:
        val: Raw Aadhaar number string
        
    Returns:
        String containing only the last 4 digits
    """
    if not isinstance(val, str):
        return ""
    # Extract only digit characters
    digits = ''.join(ch for ch in val if ch.isdigit())
    if len(digits) < 4:
        return ""
    # Keep only the last 4 digits
    return digits[-4:]

def calculate_risk_index(record: Dict[str, Any]) -> float:
    """
    Calculate risk index based on credit score or income metrics.
    
    Heuristic:
    - Credit score >= 750: low risk (0.05)
    - Credit score 600-749: medium risk (0.25)
    - Credit score < 600: high risk (0.75)
    - No credit score: fallback to income-based risk
      risk = 0.3 * (income / 200000), capped at 0.8
    
    Args:
        record: Customer record dictionary
        
    Returns:
        Float risk index between 0.0 and 1.0
    """
    # Priority 1: Credit score
    credit_score = record.get('credit_score')
    if credit_score is not None:
        try:
            cs = float(credit_score)
            if cs >= 750:
                return 0.05
            elif cs >= 600:
                return 0.25
            else:
                return 0.75
        except (ValueError, TypeError):
            pass
    
    # Priority 2: Income-based risk
    income = record.get('income')
    if income is not None:
        try:
            inc = float(income)
            # Normalize income to a scale (annual income assumed in USD)
            normalized = min(inc / 200000, 1.0)
            risk = 0.3 * normalized
            return min(risk, 0.8)
        except (ValueError, TypeError):
            pass
    
    # Default fallback
    return 0.5

def transform_batch(raw_records: List[Dict]) -> List[Dict]:
    """
    Transform batch of raw customer records into cleansed records.
    
    Each record receives:
    - masked_aadhaar: last 4 digits of original Aadhaar
    - risk_index: calculated risk score
    
    Args:
        raw_records: List of raw customer dictionaries
        
    Returns:
        List of cleaned dictionaries
    """
    cleaned = []
    for record in raw_records:
        # Work on a copy to avoid mutating original data
        cleaned_record = record.copy()
        
        # Apply Aadhaar masking
        aadhaar = cleaned_record.get('aadhaar')
        if aadhaar:
            cleaned_record['masked_aadhaar'] = mask_aadhaar(aadhaar)
        else:
            cleaned_record['masked_aadhaar'] = None
        
        # Calculate risk index
        cleaned_record['risk_index'] = calculate_risk_index(cleaned_record)
        
        cleaned.append(cleaned_record)
    
    return cleaned

def process_and_store_kyc(form_data: Dict) -> Dict:
    """
    Transform a single KYC form payload and store it in DuckDB.
    
    Args:
        form_data: Dictionary containing customer information including 'aadhaar'
        
    Returns:
        Dictionary with status and message
    """
    # Create a copy to avoid modifying the original
    record = form_data.copy()
    
    # Apply transformations
    masked_aadhaar = mask_aadhaar(record.get('aadhaar'))
    risk_index = calculate_risk_index(record)
    
    record['masked_aadhaar'] = masked_aadhaar
    record['risk_index'] = risk_index
    
    # Connect to DuckDB and insert record
    con = duckdb.connect(f"FILE={DUCKDB_PATH}")
    try:
        # Ensure target table exists
        con.execute("""
            CREATE TABLE IF NOT EXISTS cleansed_staging_data (
                id INTEGER PRIMARY KEY,
                aadhaar_masked TEXT,
                risk_index FLOAT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Insert the record
        col_names = ['id', 'aadhaar_masked', 'risk_index']
        con.execute(
            f"INSERT INTO cleansed_staging_data ({','.join(col_names)}) "
            f"VALUES ('{record.get('id', 0)}', '{record['masked_aadhaar']}', {record['risk_index']})",
            (record.get('id', 0), record['masked_aadhaar'], record['risk_index'])
        )
        
        return {
            'status': 'success',
            'message': 'KYC record successfully processed and stored'
        }
    finally:
        con.close()
