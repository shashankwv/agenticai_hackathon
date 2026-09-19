import re
import json
from typing import Optional

import streamlit as st
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_INGEST_URL = "http://127.0.0.1:8000/api/ingest"

AADHAAR_PATTERN = re.compile(r"^\d{12}$")
PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
CREDIT_SCORE_MIN = 300
CREDIT_SCORE_MAX = 900


# ---------------------------------------------------------------------------
# Backend helper
# ---------------------------------------------------------------------------
def submit_to_pipeline(form_data: dict) -> dict:
    try:
        resp = requests.post(API_INGEST_URL, json=form_data, timeout=10)
        return resp.json()
    except Exception as e:
        return {"status": "error", "message": f"Ingestion server offline (Port 8000). Please start api_bridge.py: {e}"}


# ---------------------------------------------------------------------------
# Formatting / validation helpers (unit-testable)
# ---------------------------------------------------------------------------
def sanitize_digits(value: str, max_len: int) -> str:
    """Strip all non-digit characters and truncate to max_len."""
    return re.sub(r"\D", "", value or "")[:max_len]


def format_pan(value: str) -> str:
    """Uppercase alphanumeric PAN, max 10 chars."""
    return re.sub(r"[^A-Za-z0-9]", "", value or "").upper()[:10]


def validate_aadhaar(value: str) -> Optional[str]:
    """Return an error message if Aadhaar is invalid, else None."""
    if not value:
        return "Aadhaar number is required."
    if not AADHAAR_PATTERN.fullmatch(value):
        return "Aadhaar number must be exactly 12 digits."
    return None


def validate_pan(value: str) -> Optional[str]:
    """Return an error message if PAN is invalid, else None (PAN optional)."""
    if not value:
        return None
    if not PAN_PATTERN.fullmatch(value):
        return "PAN must match format AAAAA9999A (5 letters, 4 digits, 1 letter)."
    return None


def normalize_credit_score(raw) -> Optional[int]:
    """Coerce API credit_score to int within 300-900, else None."""
    try:
        score = int(raw)
    except (TypeError, ValueError):
        return None
    if CREDIT_SCORE_MIN <= score <= CREDIT_SCORE_MAX:
        return score
    return None


def extract_credit_score(result: dict) -> Optional[int]:
    """Look for credit_score at top-level or under a 'data' key."""
    if not isinstance(result, dict):
        return None
    if "credit_score" in result:
        return normalize_credit_score(result.get("credit_score"))
    data = result.get("data")
    if isinstance(data, dict) and "credit_score" in data:
        return normalize_credit_score(data.get("credit_score"))
    return None


# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
if "aadhaar_no" not in st.session_state:
    st.session_state.aadhaar_no = ""
if "pan_no" not in st.session_state:
    st.session_state.pan_no = ""
if "credit_score" not in st.session_state:
    st.session_state.credit_score = None
if "last_result" not in st.session_state:
    st.session_state.last_result = None


def _on_aadhaar_change():
    st.session_state.aadhaar_no = sanitize_digits(st.session_state.aadhaar_no, 12)


def _on_pan_change():
    st.session_state.pan_no = format_pan(st.session_state.pan_no)


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Customer KYC Registration", page_icon="🪪", layout="centered")
st.title("Customer KYC Registration")
st.caption("Fields marked * are mandatory. Identity fields validate in real time.")

# --- Identity documents (outside the form so validation is real-time) -------
st.subheader("Identity Documents")

st.text_input(
    "Aadhaar Number *",
    key="aadhaar_no",
    max_chars=12,
    placeholder="Enter 12-digit Aadhaar number",
    help="Exactly 12 numeric digits (regex ^\\d{12}$).",
    on_change=_on_aadhaar_change,
)
aadhaar_error = validate_aadhaar(st.session_state.aadhaar_no)
if st.session_state.aadhaar_no:
    if aadhaar_error:
        st.error(aadhaar_error, icon="⚠️")
    else:
        st.caption("✅ Aadhaar format valid")

st.text_input(
    "PAN Number",
    key="pan_no",
    max_chars=10,
    placeholder="ABCDE1234F",
    help="Format: 5 letters, 4 digits, 1 letter. Auto-uppercased.",
    on_change=_on_pan_change,
)
pan_error = validate_pan(st.session_state.pan_no)
if st.session_state.pan_no:
    if pan_error:
        st.error(pan_error, icon="⚠️")
    else:
        st.caption("✅ PAN format valid")

# --- Main KYC form ----------------------------------------------------------
with st.form("kyc_form", clear_on_submit=False):
    st.subheader("Personal Details")
    full_name = st.text_input("Full Name *", placeholder="As per Aadhaar")
    col1, col2 = st.columns(2)
    with col1:
        dob = st.date_input("Date of Birth *")
    with col2:
        mobile = st.text_input("Mobile Number *", max_chars=10, placeholder="10-digit mobile")
    email = st.text_input("Email", placeholder="name@example.com")
    address = st.text_area("Residential Address *")

    st.subheader("Bureau Assessment")
    credit_score_value = st.session_state.credit_score
    credit_display = str(credit_score_value) if credit_score_value is not None else "Not yet calculated"
    st.text_input(
        "Calculated Credit Score",
        value=credit_display,
        disabled=True,
        help="Bureau-derived credit score (300-900) returned by the backend API. Read-only.",
    )
    if credit_score_value is not None:
        st.progress(
            (credit_score_value - CREDIT_SCORE_MIN) / (CREDIT_SCORE_MAX - CREDIT_SCORE_MIN),
            text=f"Credit score {credit_score_value} / {CREDIT_SCORE_MAX}",
        )

    submitted = st.form_submit_button("Submit KYC", type="primary", use_container_width=True)

# --- Submission handling ----------------------------------------------------
if submitted:
    errors = []
    if aadhaar_error:
        errors.append(aadhaar_error)
    if pan_error:
        errors.append(pan_error)
    if not full_name.strip():
        errors.append("Full Name is required.")
    mobile_clean = sanitize_digits(mobile, 10)
    if not re.fullmatch(r"^[6-9]\d{9}$", mobile_clean):
        errors.append("Mobile number must be 10 digits starting with 6-9.")
    if email.strip() and not re.fullmatch(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()):
        errors.append("Email address is not valid.")
    if not address.strip():
        errors.append("Residential Address is required.")

    if errors:
        st.error("Submission blocked. Please fix the following:")
        for err in errors:
            st.markdown(f"- {err}")
    else:
        form_data = {
            "full_name": full_name.strip(),
            "dob": dob.isoformat(),
            "mobile": mobile_clean,
            "email": email.strip(),
            "address": address.strip(),
            "aadhaar_no": st.session_state.aadhaar_no,
            "pan_no": st.session_state.pan_no,
            "form_type": "customer_kyc",
        }
        with st.spinner("Submitting to ingestion pipeline..."):
            result = submit_to_pipeline(form_data)

        score = extract_credit_score(result)
        if score is not None:
            st.session_state.credit_score = score
        st.session_state.last_result = result
        st.rerun()

# --- Render last API result -------------------------------------------------
result = st.session_state.last_result
if result is not None:
    status = str(result.get("status", "")).lower() if isinstance(result, dict) else ""
    message = result.get("message", "") if isinstance(result, dict) else str(result)

    if status == "success":
        st.success(message or "KYC submitted successfully.", icon="✅")
    elif status == "requires_pipeline":
        st.info(message or "Submission accepted and queued for pipeline processing.", icon="⏳")
    elif status == "requires_human_review":
        st.warning(message or "Submission flagged for human review.", icon="👀")
    elif status == "error":
        st.error(message or "An error occurred during ingestion.", icon="❌")
    else:
        st.warning(f"Unexpected response from API: {json.dumps(result, default=str)}")

    if st.session_state.credit_score is not None:
        st.metric("Calculated Credit Score", st.session_state.credit_score)

    with st.expander("Raw API response"):
        st.json(result)

    if st.button("Clear result"):
        st.session_state.last_result = None
        st.rerun()
