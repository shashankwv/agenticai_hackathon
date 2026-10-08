import re
import json
import uuid
import streamlit as st
import requests

# NOTE: Production deployments must point this at an HTTPS endpoint (SSN must only travel over TLS).
API_INGEST_URL = "http://127.0.0.1:8000/api/ingest"

MARITAL_STATUS_OPTIONS = ["Single", "Married", "Divorced", "Widowed"]


def submit_to_pipeline(form_data: dict) -> dict:
    try:
        # Dynamically ensure a unique ID is attached if required by API schema
        if "id" not in form_data or form_data["id"] in [None, "", "generated_id"]:
            form_data["id"] = str(uuid.uuid4())
        resp = requests.post(API_INGEST_URL, json=form_data, timeout=10)
        return resp.json()
    except Exception as e:
        return {"status": "error", "message": f"Ingestion server offline (Port 8000). Please start api_bridge.py: {e}"}


def format_identifier(raw_value: str) -> str:
    """Regex-based *formatting only* (no validation / rejection, per BRD).
    Normalises SSN, Aadhaar and PAN style identifiers into canonical shapes;
    anything else is passed through as captured.
    """
    value = (raw_value or "").strip()
    digits = re.sub(r"\D", "", value)
    # SSN: 9 digits -> XXX-XX-XXXX
    if re.fullmatch(r"\d{9}", digits):
        return f"{digits[:3]}-{digits[3:5]}-{digits[5:]}"
    # Aadhaar: 12 digits -> XXXX XXXX XXXX
    if re.fullmatch(r"\d{12}", digits):
        return " ".join(re.findall(r"\d{4}", digits))
    # PAN: AAAAA9999A -> uppercase, alphanumerics only
    pan_candidate = re.sub(r"[^A-Za-z0-9]", "", value).upper()
    if re.fullmatch(r"[A-Z]{5}\d{4}[A-Z]", pan_candidate):
        return pan_candidate
    return value


def format_name(raw_value: str) -> str:
    return re.sub(r"\s+", " ", (raw_value or "")).strip()


def mask_identifier(value: str) -> str:
    """Masks everything except the last 4 characters for on-screen acknowledgment."""
    if not value:
        return ""
    tail = value[-4:]
    return re.sub(r"[A-Za-z0-9]", "*", value[:-4]) + tail


def validate_marital_status(value) -> str:
    """Client-side required validation for the Marital Status enum.
    Returns an empty string when valid, otherwise the inline error message.
    """
    if value is None or str(value).strip() == "":
        return "Marital Status is required. Please select one option."
    if value not in MARITAL_STATUS_OPTIONS:
        return f"Marital Status must be one of: {', '.join(MARITAL_STATUS_OPTIONS)}."
    return ""


st.set_page_config(page_title="KYC Initial Intake", page_icon="\U0001F6C2", layout="centered")
st.title("Customer KYC - Initial Intake")
st.caption("Captured values are forwarded as-is to the ETL intake endpoint. No client-side validation is applied to identifier fields (per BRD); Marital Status is a mandatory selection.")

if not API_INGEST_URL.lower().startswith("https://"):
    st.warning("Local development endpoint in use (HTTP). Production must use an HTTPS ingest URL so the SSN is encrypted in transit.")

# clear_on_submit is disabled so that captured values are retained when the
# mandatory Marital Status validation blocks submission.
with st.form("kyc_form", clear_on_submit=False):
    full_name = st.text_input("Full Name", placeholder="e.g. Jane A. Doe")
    phone_number = st.number_input(
        "Phone Number",
        min_value=0,
        value=0,
        step=1,
        format="%d",
        help="Digits only, e.g. 4155550123",
    )
    ssn = st.text_input(
        "SSN",
        type="password",
        placeholder="e.g. 123-45-6789",
        help="Masked on screen. Never written to logs or analytics.",
    )
    marital_status = st.radio(
        "Marital Status *",
        options=MARITAL_STATUS_OPTIONS,
        index=None,
        horizontal=True,
        key="marital_status",
        help="Mandatory. Select exactly one option.",
    )
    marital_error_slot = st.empty()
    submitted = st.form_submit_button("Submit")

if submitted:
    marital_error = validate_marital_status(marital_status)

    if marital_error:
        # Inline error rendered directly beneath the radio group; submission is blocked.
        marital_error_slot.error(marital_error)
        st.stop()

    form_data = {
        "id": str(uuid.uuid4()),
        "form_type": "kyc_initial_intake",
        "full_name": format_name(full_name),
        "phone_number": str(int(phone_number)) if phone_number else "",
        "ssn": format_identifier(ssn),
        "marital_status": str(marital_status),
    }

    with st.spinner("Submitting to ETL intake endpoint..."):
        result = submit_to_pipeline(form_data)

    if not isinstance(result, dict):
        result = {"status": "error", "message": "Unexpected response from ingest endpoint."}

    status = str(result.get("status", "")).strip().lower()
    message = result.get("message") or result.get("detail") or ""
    record_id = result.get("id") or form_data["id"]

    if status == "success":
        st.success(f"KYC intake submitted successfully. Reference ID: {record_id}" + (f" - {message}" if message else ""))
    elif status == "requires_pipeline":
        st.info(f"Submission accepted and queued for downstream pipeline processing. Reference ID: {record_id}" + (f" - {message}" if message else ""))
    elif status == "requires_human_review":
        st.warning(f"Submission received but flagged for human review. Reference ID: {record_id}" + (f" - {message}" if message else ""))
    elif status == "error":
        st.error(f"Submission failed: {message or 'Unknown error from ingest endpoint.'}")
    else:
        st.info(f"Submission returned status '{status or 'unknown'}'." + (f" {message}" if message else ""))

    # Acknowledgment panel: SSN is masked and never emitted to logs/console/analytics.
    acknowledgment = {
        "reference_id": record_id,
        "status": status or "unknown",
        "full_name": form_data["full_name"],
        "phone_number": form_data["phone_number"],
        "ssn": mask_identifier(form_data["ssn"]),
        "marital_status": form_data["marital_status"],
    }
    with st.expander("Submission acknowledgment"):
        st.code(json.dumps(acknowledgment, indent=2), language="json")
