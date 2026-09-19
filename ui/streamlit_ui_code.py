import re
import json
import streamlit as st
import requests

API_INGEST_URL = "http://127.0.0.1:8000/api/ingest"

AADHAAR_REGEX = re.compile(r"^\d{12}$")
PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")
MOBILE_REGEX = re.compile(r"^[6-9]\d{9}$")


def submit_to_pipeline(form_data: dict) -> dict:
    try:
        resp = requests.post(API_INGEST_URL, json=form_data, timeout=10)
        return resp.json()
    except Exception as e:
        return {"status": "error", "message": f"Ingestion server offline (Port 8000). Please start api_bridge.py: {e}"}


def normalize_aadhaar(raw: str) -> str:
    # Strip spaces / hyphens commonly typed between digit groups (e.g. 1234 5678 9012)
    return re.sub(r"[\s-]", "", raw or "")


def normalize_pan(raw: str) -> str:
    return re.sub(r"\s", "", (raw or "")).upper()


def is_valid_aadhaar(value: str) -> bool:
    return bool(AADHAAR_REGEX.match(value))


def is_valid_pan(value: str) -> bool:
    return bool(PAN_REGEX.match(value))


def fetch_bureau_score(pan: str):
    """Simulates a credit bureau lookup. Returns int in 300-900 or None (pending / unavailable)."""
    if not is_valid_pan(pan):
        return None
    # Deterministic mock score derived from PAN so the UI is repeatable.
    seed = sum(ord(c) for c in pan)
    return 300 + (seed * 37) % 601


st.set_page_config(page_title="Customer 360 - KYC Registration", layout="centered")
st.title("Customer 360 - KYC Registration")
st.caption("Extended KYC form with Aadhaar validation and bureau credit score display.")

if "credit_score" not in st.session_state:
    st.session_state.credit_score = None
if "credit_score_state" not in st.session_state:
    st.session_state.credit_score_state = "pending"  # pending | available | unavailable

# ---------------------------------------------------------------
# Bureau lookup (outside the form: st.button is not permitted in st.form)
# ---------------------------------------------------------------
with st.expander("Credit Bureau Lookup", expanded=True):
    lookup_pan = normalize_pan(st.text_input("PAN for bureau lookup", max_chars=10, placeholder="ABCDE1234F", key="lookup_pan"))
    if lookup_pan and not is_valid_pan(lookup_pan):
        st.error("PAN must match format AAAAA9999A (5 letters, 4 digits, 1 letter).")
    if st.button("Fetch Credit Score from Bureau"):
        score = fetch_bureau_score(lookup_pan)
        if score is None:
            st.session_state.credit_score = None
            st.session_state.credit_score_state = "unavailable"
        else:
            st.session_state.credit_score = score
            st.session_state.credit_score_state = "available"

# ---------------------------------------------------------------
# KYC Form
# ---------------------------------------------------------------
with st.form("kyc_form"):
    st.subheader("Customer Details")
    full_name = st.text_input("Full Name", max_chars=100)
    dob = st.date_input("Date of Birth")
    mobile = st.text_input("Mobile Number", max_chars=10, placeholder="9876543210")
    email = st.text_input("Email")
    address = st.text_area("Address", height=80)

    st.subheader("Identity Documents")
    pan_raw = st.text_input("PAN Number", max_chars=10, placeholder="ABCDE1234F")
    pan_error = st.empty()

    aadhaar_raw = st.text_input(
        "Aadhaar Number",
        max_chars=14,
        placeholder="123456789012",
        help="Exactly 12 numeric digits. Spaces or hyphens are removed automatically.",
    )
    aadhaar_error = st.empty()

    st.subheader("Calculated Credit Score (read-only)")
    cs_state = st.session_state.credit_score_state
    cs_value = st.session_state.credit_score
    if cs_state == "available" and cs_value is not None:
        cs_display = str(cs_value)
        cs_help = "Populated from bureau response (range 300-900). Not editable."
    elif cs_state == "unavailable":
        cs_display = "N/A - bureau returned no score"
        cs_help = "Bureau lookup did not return a score for the provided PAN."
    else:
        cs_display = "Pending - awaiting bureau response"
        cs_help = "Run the bureau lookup above to populate this field."
    st.text_input("Calculated Credit Score", value=cs_display, disabled=True, help=cs_help)
    if cs_state == "available" and cs_value is not None:
        st.progress((cs_value - 300) / 600.0, text=f"Score band: {cs_value} / 900")

    submitted = st.form_submit_button("Submit KYC")

# ---------------------------------------------------------------
# Validation & Submission
# ---------------------------------------------------------------
if submitted:
    errors = []
    aadhaar = normalize_aadhaar(aadhaar_raw)
    pan = normalize_pan(pan_raw)

    if not is_valid_aadhaar(aadhaar):
        aadhaar_error.error("Invalid Aadhaar: must be exactly 12 numeric digits (regex ^\\d{12}$).")
        errors.append("aadhaar")
    else:
        aadhaar_error.empty()

    if not is_valid_pan(pan):
        pan_error.error("Invalid PAN: expected format AAAAA9999A.")
        errors.append("pan")
    else:
        pan_error.empty()

    if not full_name.strip():
        st.error("Full Name is required.")
        errors.append("full_name")

    if mobile and not MOBILE_REGEX.match(mobile):
        st.error("Mobile Number must be 10 digits starting with 6-9.")
        errors.append("mobile")

    if errors:
        st.error("Submission blocked. Please fix the highlighted fields.")
    else:
        form_data = {
            "form_type": "kyc_registration",
            "full_name": full_name.strip(),
            "dob": dob.isoformat() if dob else None,
            "mobile": mobile,
            "email": email.strip(),
            "address": address.strip(),
            "pan": pan,
            "aadhaar": aadhaar,
            "aadhaar_masked": "XXXX-XXXX-" + aadhaar[-4:],
            "credit_score": st.session_state.credit_score,
            "credit_score_state": st.session_state.credit_score_state,
        }

        with st.spinner("Submitting to ingestion pipeline..."):
            result = submit_to_pipeline(form_data)

        status = (result or {}).get("status", "error")
        message = (result or {}).get("message", "")

        if status == "success":
            st.success(f"KYC submitted successfully. {message}")
        elif status == "requires_pipeline":
            st.info(f"Submission accepted and queued for downstream pipeline processing. {message}")
        elif status == "requires_human_review":
            st.warning(f"Submission flagged for human review. {message}")
        else:
            st.error(f"Submission failed: {message or 'Unknown error'}")

        with st.expander("Payload sent"):
            safe_payload = dict(form_data)
            safe_payload["aadhaar"] = safe_payload["aadhaar_masked"]
            st.code(json.dumps(safe_payload, indent=2), language="json")
        with st.expander("Raw pipeline response"):
            st.code(json.dumps(result, indent=2, default=str), language="json")
