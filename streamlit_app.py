import re
import json
import uuid
import streamlit as st
import requests

API_INGEST_URL = "http://127.0.0.1:8000/api/ingest"

# Regex patterns used purely for display formatting (non-blocking, no validation)
UUID_PATTERN = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
AADHAAR_PATTERN = re.compile(r"^\s*(\d{4})\s*-?\s*(\d{4})\s*-?\s*(\d{4})\s*$")
PAN_PATTERN = re.compile(r"^\s*([A-Za-z]{5})\s*([0-9]{4})\s*([A-Za-z])\s*$")

MARITAL_STATUS_OPTIONS = ["Single", "Married", "Divorced", "Widowed"]


def format_identifier_preview(value: str) -> str:
    """Return a display-friendly version of an identifier using regex.
    Aadhaar -> 'XXXX XXXX XXXX', PAN -> upper-case 'AAAAA9999A'. Anything else is returned untouched.
    This is cosmetic only; the raw value is what gets submitted.
    """
    if not isinstance(value, str):
        return value
    aadhaar_match = AADHAAR_PATTERN.match(value)
    if aadhaar_match:
        return " ".join(aadhaar_match.groups())
    pan_match = PAN_PATTERN.match(value)
    if pan_match:
        return "".join(pan_match.groups()).upper()
    return value


def validate_marital_status(value) -> str:
    """Return an inline error message if Marital Status is not selected, else an empty string."""
    if value is None or value not in MARITAL_STATUS_OPTIONS:
        return "Marital Status is required. Please select one option."
    return ""


def build_payload(full_name: str, phone_number, ssn: str, marital_status: str) -> dict:
    """Map form fields to the intake payload, binding the radio value to 'marital_status'."""
    return {
        "full_name": full_name,
        "phone_number": int(phone_number),
        "ssn": ssn,
        "marital_status": marital_status,
    }


def submit_to_pipeline(form_data: dict) -> dict:
    try:
        # Dynamically ensure a unique ID is attached if required by API schema
        current_id = form_data.get("id")
        if not isinstance(current_id, str) or not UUID_PATTERN.match(current_id):
            form_data["id"] = str(uuid.uuid4())
        resp = requests.post(API_INGEST_URL, json=form_data, timeout=10)
        return resp.json()
    except Exception as e:
        return {"status": "error", "message": f"Ingestion server offline (Port 8000). Please start api_bridge.py: {e}"}


st.set_page_config(page_title="KYC Initial Intake", page_icon="\U0001FAAA")
st.title("Customer KYC - Initial Intake")
st.caption("Per BRD: no client-side validations are enforced on text fields. Marital Status is a mandatory selection. Raw payload is posted to the intake ingestion endpoint.")

with st.form("kyc_form", clear_on_submit=False):
    full_name = st.text_input("Full Name")
    phone_number = st.number_input("Phone Number", min_value=0, step=1, format="%d")
    ssn = st.text_input("SSN")
    marital_status = st.radio(
        "Marital Status *",
        options=MARITAL_STATUS_OPTIONS,
        index=None,
        horizontal=True,
        key="marital_status",
    )
    marital_error_placeholder = st.empty()
    submitted = st.form_submit_button("Submit")

if submitted:
    marital_error = validate_marital_status(marital_status)
    if marital_error:
        # Block submission and show inline required-field error directly under the radio group
        marital_error_placeholder.error(marital_error)
        st.stop()

    form_data = build_payload(full_name, phone_number, ssn, marital_status)

    with st.expander("Payload preview", expanded=False):
        st.code(json.dumps(form_data, indent=2), language="json")
        formatted_preview = format_identifier_preview(ssn)
        if formatted_preview != ssn:
            st.write(f"Identifier display format: `{formatted_preview}`")

    with st.spinner("Submitting to intake pipeline..."):
        result = submit_to_pipeline(form_data)

    status = str(result.get("status", "")).lower() if isinstance(result, dict) else ""
    message = result.get("message", "") if isinstance(result, dict) else str(result)

    if status == "success":
        st.success(message or f"KYC intake submitted successfully. Record ID: {form_data.get('id')}")
    elif status == "requires_pipeline":
        st.info(message or "Submission accepted and queued for downstream pipeline processing.")
    elif status == "requires_human_review":
        st.warning(message or "Submission received and flagged for human review.")
    elif status == "error":
        st.error(message or "Submission failed.")
    else:
        st.warning(f"Unrecognized response from ingestion endpoint: {result}")

    with st.expander("Raw API response", expanded=False):
        st.json(result if isinstance(result, dict) else {"response": str(result)})
