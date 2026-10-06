import re
import json
import streamlit as st
import requests

API_INGEST_URL = "http://127.0.0.1:8000/api/ingest"

MARITAL_STATUS_OPTIONS = ["Single", "Married", "Divorced", "Widowed"]


def submit_to_pipeline(form_data: dict) -> dict:
    try:
        resp = requests.post(API_INGEST_URL, json=form_data, timeout=10)
        return resp.json()
    except Exception as e:
        return {"status": "error", "message": f"Ingestion server offline (Port 8000). Please start api_bridge.py: {e}"}


def validate_marital_status(marital_status) -> str:
    """Return an error message if marital status is not selected, else empty string."""
    if marital_status is None or marital_status not in MARITAL_STATUS_OPTIONS:
        return "Marital Status is required. Please select one option."
    return ""


st.set_page_config(page_title="KYC Initial Intake", page_icon="🪪", layout="centered")

st.title("Customer KYC Updates")
st.subheader("KYC Initial Intake Form")
st.caption("Captures Full Name, Phone Number, SSN and Marital Status for downstream ETL consumption. Email, address, document upload and IDV checks are out of scope for this intake.")

with st.form("kyc_form", clear_on_submit=False):
    full_name = st.text_input("Full Name", placeholder="e.g. Jane A. Doe")
    phone_number = st.number_input(
        "Phone Number",
        min_value=0,
        step=1,
        value=0,
        format="%d",
        help="Digits only (numeric input per BRD).",
    )
    ssn = st.text_input("SSN", type="password", placeholder="Social Security Number")
    marital_status = st.radio(
        "Marital Status *",
        options=MARITAL_STATUS_OPTIONS,
        index=None,
        horizontal=True,
        key="marital_status",
        help="Required. Select one option.",
    )
    marital_status_error_placeholder = st.empty()
    submitted = st.form_submit_button("Submit KYC Intake")

if submitted:
    # Validation applies only to the Marital Status field (required per Jira story).
    marital_status_error = validate_marital_status(marital_status)

    if marital_status_error:
        # Inline required-field error placed directly beneath the radio group; block submission.
        marital_status_error_placeholder.error(marital_status_error)
    else:
        # No client-side validation for other fields per BRD - payload is forwarded as entered.
        form_data = {
            "full_name": full_name,
            "phone_number": str(int(phone_number)),
            "ssn": ssn,
            "marital_status": marital_status,
        }

        with st.spinner("Submitting to intake pipeline..."):
            result = submit_to_pipeline(form_data)

        status = str(result.get("status", "error")).lower() if isinstance(result, dict) else "error"
        message = result.get("message", "") if isinstance(result, dict) else str(result)

        if status == "success":
            st.success(message or "KYC intake submitted successfully. Record queued for ETL consumption.")
        elif status == "requires_pipeline":
            st.info(message or "Submission accepted. Record is pending downstream pipeline processing.")
        elif status == "requires_human_review":
            st.warning(message or "Submission received but has been flagged for human review.")
        else:
            st.error(message or "Submission failed. Please try again or contact support.")

        with st.expander("Submission details"):
            st.code(json.dumps({"request": {**form_data, "ssn": "***REDACTED***"}, "response": result}, indent=2), language="json")
