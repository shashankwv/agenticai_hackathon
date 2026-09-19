import re
import json
import streamlit as st
import requests

API_INGEST_URL = "http://127.0.0.1:8000/api/ingest"
BUREAU_API_URL = "http://127.0.0.1:8000/api/bureau/credit_score"

AADHAAR_PATTERN = re.compile(r"^\d{12}$")
PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")


def submit_to_pipeline(form_data: dict) -> dict:
    try:
        resp = requests.post(API_INGEST_URL, json=form_data, timeout=10)
        return resp.json()
    except Exception as e:
        return {"status": "error", "message": f"Ingestion server offline (Port 8000). Please start api_bridge.py: {e}"}


def validate_aadhaar(value: str):
    """Return (is_valid, error_message). Valid only if exactly 12 numeric digits."""
    value = (value or "").strip()
    if value == "":
        return False, "Aadhaar Number is required."
    if AADHAAR_PATTERN.match(value):
        return True, ""
    if not value.isdigit():
        return False, "Aadhaar Number must contain numeric digits only (0-9)."
    if len(value) < 12:
        return False, f"Aadhaar Number must be exactly 12 digits. You entered {len(value)} (too short)."
    return False, f"Aadhaar Number must be exactly 12 digits. You entered {len(value)} (too long)."


def validate_pan(value: str):
    """Return (is_valid, error_message). PAN is optional but must match AAAAA9999A if provided."""
    value = (value or "").strip().upper()
    if value == "":
        return True, ""
    if PAN_PATTERN.match(value):
        return True, ""
    return False, "PAN must be 10 characters in the format AAAAA9999A (5 letters, 4 digits, 1 letter)."


def format_aadhaar(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    return " ".join([digits[i:i + 4] for i in range(0, len(digits), 4)])


def fetch_credit_score(aadhaar: str, pan: str):
    """Call the bureau integration API and return credit_score or None if unavailable."""
    try:
        resp = requests.get(BUREAU_API_URL, params={"aadhaar": aadhaar, "pan": pan}, timeout=10)
        data = resp.json()
        return data.get("credit_score")
    except Exception:
        return None


st.set_page_config(page_title="Customer KYC Registration", page_icon="🪪")
st.title("Customer KYC Registration")
st.caption("Fields marked with * are required.")

if "credit_score" not in st.session_state:
    st.session_state["credit_score"] = None

# Identity fields live outside the form so validation feedback is real-time (rerun on every change)
st.subheader("Identity Documents")
aadhaar_raw = st.text_input(
    "Aadhaar Number *",
    max_chars=12,
    placeholder="12-digit numeric Aadhaar",
    key="aadhaar_input",
    help="Exactly 12 numeric digits, e.g. 123412341234",
)
aadhaar_valid, aadhaar_error = validate_aadhaar(aadhaar_raw)
if aadhaar_raw and not aadhaar_valid:
    st.error(aadhaar_error, icon="⚠️")
elif aadhaar_valid:
    st.success(f"Aadhaar format valid: {format_aadhaar(aadhaar_raw)}", icon="✅")

pan_raw = st.text_input("PAN (optional)", max_chars=10, placeholder="ABCDE1234F", key="pan_input")
pan_value = (pan_raw or "").strip().upper()
pan_valid, pan_error = validate_pan(pan_value)
if pan_raw and not pan_valid:
    st.error(pan_error, icon="⚠️")

st.subheader("Bureau Integration")
col_a, col_b = st.columns([2, 1])
with col_b:
    if st.button("Fetch Credit Score", disabled=not aadhaar_valid, use_container_width=True):
        st.session_state["credit_score"] = fetch_credit_score(aadhaar_raw.strip(), pan_value)
with col_a:
    score = st.session_state.get("credit_score")
    display_value = str(score) if score is not None else "Not available"
    # Read-only, non-editable display bound to the bureau credit_score value
    st.text_input("Calculated Credit Score (read-only)", value=display_value, disabled=True, key="credit_score_display")

with st.form("kyc_form"):
    st.subheader("Customer Details")
    full_name = st.text_input("Full Name *")
    dob = st.date_input("Date of Birth *")
    email = st.text_input("Email *")
    phone = st.text_input("Mobile Number *", max_chars=10)
    address = st.text_area("Residential Address *")
    consent = st.checkbox("I consent to KYC verification and bureau credit checks *")

    can_submit = aadhaar_valid and pan_valid
    if not can_submit:
        st.caption("Submission is blocked until the Aadhaar (and PAN, if provided) fields are valid.")
    submitted = st.form_submit_button("Submit KYC", disabled=not can_submit)

    if submitted:
        errors = []
        if not aadhaar_valid:
            errors.append(aadhaar_error)
        if not pan_valid:
            errors.append(pan_error)
        if not full_name.strip():
            errors.append("Full Name is required.")
        if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()):
            errors.append("A valid Email is required.")
        if not re.match(r"^[6-9]\d{9}$", phone.strip()):
            errors.append("Mobile Number must be 10 digits starting with 6-9.")
        if not address.strip():
            errors.append("Residential Address is required.")
        if not consent:
            errors.append("Consent is required to proceed.")

        if errors:
            for err in errors:
                st.error(err)
        else:
            form_data = {
                "form_type": "customer_kyc",
                "full_name": full_name.strip(),
                "date_of_birth": dob.isoformat(),
                "email": email.strip(),
                "phone": phone.strip(),
                "address": address.strip(),
                "aadhaar_number": aadhaar_raw.strip(),
                "pan_number": pan_value or None,
                "credit_score": st.session_state.get("credit_score"),
                "consent": consent,
            }
            with st.spinner("Submitting to ingestion pipeline..."):
                result = submit_to_pipeline(form_data)
            if not isinstance(result, dict):
                result = {"status": "error", "message": f"Unexpected response: {result}"}
            status = result.get("status", "error")
            message = result.get("message", "")
            if result.get("credit_score") is not None:
                st.session_state["credit_score"] = result["credit_score"]
            if status == "success":
                st.success(message or "KYC submitted successfully.")
            elif status == "requires_pipeline":
                st.info(message or "Submission accepted and queued for pipeline processing.")
            elif status == "requires_human_review":
                st.warning(message or "Submission flagged for human review.")
            elif status == "error":
                st.error(message or "Submission failed.")
            else:
                st.info(f"Response: {json.dumps(result)}")
