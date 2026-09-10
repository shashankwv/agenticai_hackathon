import datetime
import re

def _clean_string(value, max_length=None):
    """Converts value to string, strips whitespace, and truncates if max_length is provided."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    if max_length and len(s) > max_length:
        return s[:max_length]
    return s

def _clean_phone_number(value, max_length=None):
    """Cleans phone number by removing non-digit characters."""
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    # Remove all non-digit characters
    cleaned_number = re.sub(r'\D', '', s)
    if not cleaned_number:
        return None
    if max_length and len(cleaned_number) > max_length:
        return cleaned_number[:max_length]
    return cleaned_number

def _parse_date(value):
    """Parses a date string into a datetime.date object."""
    if value is None:
        return None
    if isinstance(value, datetime.date):
        return value
    if isinstance(value, datetime.datetime):
        return value.date()

    s = str(value).strip()
    if not s:
        return None

    # Try common date formats
    date_formats = [
        "%Y-%m-%d",  # YYYY-MM-DD
        "%m/%d/%Y",  # MM/DD/YYYY
        "%d-%m-%Y",  # DD-MM-YYYY
        "%Y%m%d"     # YYYYMMDD
    ]
    for fmt in date_formats:
        try:
            return datetime.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None

def transform_data(raw_records: list[dict]) -> list[dict]:
    """
    Transforms, validates, and cleans raw party records to match the target EntitySchema.

    Args:
        raw_records: A list of dictionaries, where each dictionary represents a raw record.

    Returns:
        A list of dictionaries, where each dictionary represents a transformed and validated record.
        Records that fail critical validation (e.g., missing required fields) are skipped.
    """
    transformed_records = []
    for i, raw_record in enumerate(raw_records):
        transformed_record = {}
        record_id = raw_record.get('id_prim') or f"record_idx_{i}" # For logging purposes

        # --- Required Fields ---

        # id_prim: Primary Party Identifier (VARCHAR(50), required, primary key)
        id_prim = _clean_string(raw_record.get('id_prim'), max_length=50)
        if not id_prim:
            print(f"Warning: Skipping record {record_id} due to missing or invalid 'id_prim'.")
            continue
        transformed_record['id_prim'] = id_prim

        # plss: Prospect or Active Status (VARCHAR(20), required)
        plss = _clean_string(raw_record.get('plss'), max_length=20)
        if not plss:
            print(f"Warning: Skipping record {record_id} due to missing or invalid 'plss'.")
            continue
        transformed_record['plss'] = plss

        # first_name: First Name (VARCHAR(100), required)
        first_name = _clean_string(raw_record.get('first_name'), max_length=100)
        if not first_name:
            print(f"Warning: Skipping record {record_id} due to missing or invalid 'first_name'.")
            continue
        transformed_record['first_name'] = first_name

        # last_name: Last Name (VARCHAR(100), required)
        last_name = _clean_string(raw_record.get('last_name'), max_length=100)
        if not last_name:
            print(f"Warning: Skipping record {record_id} due to missing or invalid 'last_name'.")
            continue
        transformed_record['last_name'] = last_name

        # aadhaar_no: Aadhaar Number (VARCHAR(12), required)
        # Clean by removing spaces/dashes before checking length
        aadhaar_no_raw = raw_record.get('aadhaar_no')
        if aadhaar_no_raw is not None:
            aadhaar_no_cleaned = re.sub(r'[\s-]', '', str(aadhaar_no_raw)).strip()
            if aadhaar_no_cleaned and len(aadhaar_no_cleaned) <= 12:
                transformed_record['aadhaar_no'] = aadhaar_no_cleaned
            else:
                print(f"Warning: Skipping record {record_id} due to missing or invalid 'aadhaar_no'.")
                continue
        else:
            print(f"Warning: Skipping record {record_id} due to missing 'aadhaar_no'.")
            continue

        # --- Optional Fields ---

        # tax_id_type: Tax Identification Type (VARCHAR(20), optional)
        transformed_record['tax_id_type'] = _clean_string(raw_record.get('tax_id_type'), max_length=20)

        # tax_id: Tax Identification Number (VARCHAR(50), optional)
        transformed_record['tax_id'] = _clean_string(raw_record.get('tax_id'), max_length=50)

        # dob: Date of Birth (DATE, optional)
        dob_value = raw_record.get('dob')
        transformed_record['dob'] = _parse_date(dob_value)
        if dob_value and not transformed_record['dob']:
            print(f"Warning: Record {record_id} - 'dob' value '{dob_value}' could not be parsed as a date. Set to None.")

        # legal_addr: Legal Address (VARCHAR(255), optional)
        transformed_record['legal_addr'] = _clean_string(raw_record.get('legal_addr'), max_length=255)

        # prim_addr: Primary Address (VARCHAR(255), optional)
        transformed_record['prim_addr'] = _clean_string(raw_record.get('prim_addr'), max_length=255)

        # phone_number: Phone Number (VARCHAR(20), optional)
        transformed_record['phone_number'] = _clean_phone_number(raw_record.get('phone_number'), max_length=20)

        # email_id: Email Address (VARCHAR(100), optional)
        email_id = _clean_string(raw_record.get('email_id'), max_length=100)
        transformed_record['email_id'] = email_id.lower() if email_id else None

        # alternate_phone: Alternate Phone Number (VARCHAR(20), optional)
        transformed_record['alternate_phone'] = _clean_phone_number(raw_record.get('alternate_phone'), max_length=20)

        transformed_records.append(transformed_record)

    return transformed_records

if __name__ == "__main__":
    # Example Usage
    raw_data = [
        {
            "id_prim": "P001",
            "plss": "ACTIVE",
            "first_name": "  John ",
            "last_name": "Doe",
            "tax_id_type": "PAN",
            "tax_id": "ABCDE1234F",
            "dob": "1980-01-15",
            "legal_addr": "123 Main St, Anytown, USA",
            "prim_addr": "123 Main St, Anytown, USA",
            "phone_number": "+1 (555) 123-4567",
            "email_id": "JOHN.DOE@example.com",
            "aadhaar_no": "1234 5678 9012",
            "alternate_phone": "555-987-6543"
        },
        {
            "id_prim": "P002",
            "plss": "PROSPECT",
            "first_name": "Jane",
            "last_name": "Smith",
            "dob": "1992/03/20",
            "email_id": "jane.smith@test.com  ",
            "aadhaar_no": "9876-5432-1098",
            "phone_number": "1234567890123456789012345" # Too long
        },
        {
            "id_prim": "P003",
            "plss": "ACTIVE",
            "first_name": "Alice",
            "last_name": "Brown",
            "dob": "invalid-date", # Invalid date
            "aadhaar_no": "111122223333",
            "tax_id": None,
            "phone_number": "" # Empty phone
        },
        {
            # Missing required fields: id_prim, first_name, aadhaar_no
            "plss": "ACTIVE",
            "last_name": "Invalid",
            "email_id": "invalid@example.com",
            "dob": "2000-01-01"
        },
        {
            "id_prim": "P005",
            "plss": "ACTIVE",
            "first_name": "Bob",
            "last_name": "White",
            "aadhaar_no": "12345678901234567890", # Too long
            "dob": datetime.date(1975, 6, 30) # Already a date object
        },
        {
            "id_prim": "P006",
            "plss": "ACTIVE",
            "first_name": "Charlie",
            "last_name": "Green",
            "aadhaar_no": "12345678901", # Valid length
            "dob": "19950701" # YYYYMMDD format
        }
    ]

    print("--- Raw Data ---")
    for record in raw_data:
        print(record)
    print("\n" + "="*50 + "\n")

    transformed_data = transform_data(raw_data)

    print("\n--- Transformed Data ---")
    for record in transformed_data:
        print(record)
    print("\n" + "="*50 + "\n")

    print(f"Total raw records: {len(raw_data)}")
    print(f"Total transformed records: {len(transformed_data)}")

    # Expected output for P001
    expected_p001 = {
        'id_prim': 'P001',
        'plss': 'ACTIVE',
        'first_name': 'John',
        'last_name': 'Doe',
        'tax_id_type': 'PAN',
        'tax_id': 'ABCDE1234F',
        'dob': datetime.date(1980, 1, 15),
        'legal_addr': '123 Main St, Anytown, USA',
        'prim_addr': '123 Main St, Anytown, USA',
        'phone_number': '15551234567',
        'email_id': 'john.doe@example.com',
        'aadhaar_no': '123456789012',
        'alternate_phone': '5559876543'
    }
    print("\nVerification for P001:")
    if transformed_data and transformed_data[0] == expected_p001:
        print("P001 transformation successful!")
    else:
        print("P001 transformation failed or record not found.")
        if transformed_data:
            print("Actual:", transformed_data[0])
            print("Expected:", expected_p001)
