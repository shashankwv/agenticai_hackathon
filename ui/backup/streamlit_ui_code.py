import re
import json
import streamlit as st
import requests

# ---------------------------------------------------------------------------
# Customer KYC Updates - KYC Initial Intake Form
# Per BRD: NO client-side validations (no required checks, format masks,
# length limits, or regex) EXCEPT where explicitly required by the Jira story.
# Jira story: 'Marital Status' radio group is MANDATORY - block Submit and
# display an inline required-field error until one option is selected.
# Raw payload is POSTed to the ETL intake endpoint.
# Out of scope: document upload, email/address fields, IDV API calls.
# ---------------------------------------------------------------------------

API_INGEST_URL = "http://127.0.0.1:8000/api/ingest"

MARITAL_STATUS_OPTIONS = ["Single", "Married", "Divorced", "Widowed"]
MARITAL_STATUS_REQUIRED_MSG = "Marital Status is required. Please select one option."


def submit_to_pipeline(form_data: dict) -> dict:
    try:
        resp = requests.post(API_INGEST_URL, json=form_data, timeout=10)
        return resp.json()
    except Exception as e:
        return {"status": "error", "message": f"Ingestion server offline (Port 8000). Please start api_bridge.py: {e}"}


def validate_marital_status(marital_status) -> str | None:
    """Return an error message if marital_status is not selected, else None.
    Exposed as a plain function so it can be unit-tested."""
    if marital_status is None or marital_status not in MARITAL_STATUS_OPTIONS:
        return MARITAL_STATUS_REQUIRED_MSG
    return None


def build_payload(full_name, phone_number, ssn, marital_status) -> dict:
    """Build raw payload: {full_name, phone_number, ssn, marital_status}.
    Exposed as a plain function so payload inclusion can be unit-tested."""
    return {
        "full_name": full_name,
        "phone_number": int(phone_number) if phone_number is not None else None,
        "ssn": ssn,
        "marital_status": marital_status,
    }


st.set_page_config(page_title="KYC Initial Intake", page_icon="\U0001FAAA", layout="centered")

st.title("Customer KYC Initial Intake")
st.caption("Enter the customer's details below and click Submit to send the record to the ETL intake pipeline.")

with st.form("kyc_form"):
    full_name = st.text_input("Full Name", placeholder="e.g. Jane Doe")
    phone_number = st.number_input("Phone Number", value=0, step=1, format="%d")
    ssn = st.text_input("SSN", placeholder="Social Security Number")
    # Mandatory Marital Status radio group - positioned directly after SSN and above Submit.
    # Default: none selected (index=None).
    marital_status = st.radio(
        "Marital Status *",
        options=MARITAL_STATUS_OPTIONS,
        index=None,
        horizontal=True,
        key="marital_status",
    )
    # Inline placeholder for the required-field error, rendered directly beneath the radio group.
    marital_status_error_slot = st.empty()
    submitted = st.form_submit_button("Submit")

if submitted:
    validation_error = validate_marital_status(marital_status)

    if validation_error:
        # Block submission and show inline required-field error.
        marital_status_error_slot.error(validation_error, icon="\u26a0\ufe0f")
        st.toast("Please select a Marital Status before submitting", icon="\u26a0\ufe0f")
    else:
        # Build raw payload exactly as specified: {full_name, phone_number, ssn, marital_status}
        form_data = build_payload(full_name, phone_number, ssn, marital_status)

        with st.spinner("Submitting to ETL intake pipeline..."):
            result = submit_to_pipeline(form_data)

        status = str(result.get("status", "")).lower()
        message = result.get("message", "")

        if status == "success":
            st.success(message or "KYC record submitted successfully.")
            st.toast("Submission successful", icon="\u2705")
        elif status == "requires_pipeline":
            st.info(message or "Submission accepted and queued for downstream pipeline processing.")
            st.toast("Queued for pipeline", icon="\u2139\ufe0f")
        elif status == "requires_human_review":
            st.warning(message or "Submission accepted but flagged for human review.")
            st.toast("Flagged for human review", icon="\u26a0\ufe0f")
        elif status == "error":
            st.error(message or "Submission failed. Please try again.")
            st.toast("Submission failed", icon="\u274c")
        else:
            st.info(f"Unexpected response from intake endpoint: {json.dumps(result)}")

        with st.expander("Raw server response"):
            st.json(result)


# ---------------------------------------------------------------------------
# Unit tests (run with: python -m pytest <this_file>.py)
# These cover the required-field validation and payload inclusion for
# marital_status without needing a live Streamlit session or API server.
# ---------------------------------------------------------------------------

def test_marital_status_required_when_none():
    assert validate_marital_status(None) == MARITAL_STATUS_REQUIRED_MSG


def test_marital_status_required_when_invalid_option():
    assert validate_marital_status("Unknown") == MARITAL_STATUS_REQUIRED_MSG


def test_marital_status_valid_options_pass_validation():
    for option in MARITAL_STATUS_OPTIONS:
        assert validate_marital_status(option) is None


def test_payload_includes_marital_status():
    payload = build_payload("Jane Doe", 5551234567, "123-45-6789", "Married")
    assert "marital_status" in payload
    assert payload["marital_status"] == "Married"
    assert payload["full_name"] == "Jane Doe"
    assert payload["phone_number"] == 5551234567
    assert payload["ssn"] == "123-45-6789"


def test_payload_keys_exact():
    payload = build_payload("", 0, "", "Single")
    assert set(payload.keys()) == {"full_name", "phone_number", "ssn", "marital_status"}
