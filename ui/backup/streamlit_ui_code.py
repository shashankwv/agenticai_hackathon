import re
import json
import streamlit as st
import requests
import uuid

API_INGEST_URL = "http://127.0.0.1:8000/api/ingest"

# Placeholder identifiers that must be replaced with a real UUID before ingestion.
# Kept as a module-level constant so no literal sentinel is hardcoded inside logic.
PLACEHOLDER_IDS = (None, "", "generated_id")

# Regex patterns used purely for *formatting* (normalisation), never for rejection.
# Per BRD there is NO client-side validation: unmatched values pass through untouched.
AADHAAR_PATTERN = re.compile(r"^\s*(\d{4})\s*-?\s*(\d{4})\s*-?\s*(\d{4})\s*$")
PAN_PATTERN = re.compile(r"^\s*([A-Za-z]{5})\s*-?\s*(\d{4})\s*-?\s*([A-Za-z])\s*$")
SSN_PATTERN = re.compile(r"^\s*(\d{3})\s*-?\s*(\d{2})\s*-?\s*(\d{4})\s*$")
NON_DIGIT_PATTERN = re.compile(r"\D+")


def format_identifier(value: str) -> str:
    """Normalise Aadhaar / PAN / SSN style identifiers via regex formatting only.
    Any value that does not match a known layout is returned unchanged (free-form passthrough)."""
    if not isinstance(value, str):
        return value
    m = AADHAAR_PATTERN.match(value)
    if m:
        return "-".join(m.groups())
    m = PAN_PATTERN.match(value)
    if m:
        return (m.group(1) + m.group(2) + m.group(3)).upper()
    m = SSN_PATTERN.match(value)
    if m:
        return "-".join(m.groups())
    return value


def format_phone(value: str) -> str:
    """Strip formatting characters so the phone number is passed through as digits only.
    No length or pattern validation is performed."""
    if not isinstance(value, str):
        return value
    return NON_DIGIT_PATTERN.sub("", value)


def submit_to_pipeline(form_data: dict) -> dict:
    try:
        # Dynamically ensure a unique ID is attached if required by API schema
        if "id" not in form_data or form_data["id"] in PLACEHOLDER_IDS:
            form_data["id"] = str(uuid.uuid4())
        resp = requests.post(API_INGEST_URL, json=form_data, timeout=10)
        return resp.json()
    except Exception as e:
        return {"status": "error", "message": f"Ingestion server offline (Port 8000). Please start api_bridge.py: {e}"}


st.set_page_config(page_title="KYC Initial Intake", page_icon="🪪", layout="centered")
st.title("Customer KYC Updates")
st.subheader("KYC Initial Intake")
st.caption("All fields are free-form passthrough. Data is forwarded directly to the ETL intake pipeline.")

with st.form("kyc_form", clear_on_submit=False):
    full_name = st.text_input("Full Name", key="full_name")
    phone_number = st.text_input(
        "Phone Number",
        key="phone_number",
        help="Numeric input. Non-digit characters are stripped before submission.",
    )
    # SSN is masked on screen (password-style). It is never echoed, logged, or sent to analytics.
    ssn = st.text_input("SSN", type="password", key="ssn")
    submitted = st.form_submit_button("Submit")

if submitted:
    form_data = {
        "full_name": full_name,
        "phone_number": format_phone(phone_number),
        "ssn": format_identifier(ssn),
    }

    with st.spinner("Submitting to intake pipeline..."):
        result = submit_to_pipeline(form_data)

    # Defensive: ensure the response is a dict before reading status
    if not isinstance(result, dict):
        try:
            result = json.loads(result)
        except Exception:
            result = {"status": "error", "message": "Unexpected response from ingestion API."}

    status = str(result.get("status", "error")).lower()
    message = result.get("message", "")
    record_id = result.get("id", form_data.get("id"))

    # Only submit success/failure state is displayed. Payload contents (incl. SSN) are never rendered.
    if status == "success":
        st.success(f"KYC intake submitted successfully. Reference ID: {record_id}")
    elif status == "requires_pipeline":
        st.info(f"Submission accepted and queued for pipeline processing. Reference ID: {record_id}" + (f" — {message}" if message else ""))
    elif status == "requires_human_review":
        st.warning(f"Submission received and flagged for human review. Reference ID: {record_id}" + (f" — {message}" if message else ""))
    else:
        st.error(message or "Submission failed. Please try again.")
