import re
import json
import streamlit as st
import requests

API_INGEST_URL = "http://127.0.0.1:8000/api/ingest"

# ---------------------------------------------------------------------------
# Validation / formatting helpers (unit-testable, pure functions)
# ---------------------------------------------------------------------------
AADHAAR_PATTERN = re.compile(r"^\d{12}$")
PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
AADHAAR_ERROR = "Aadhaar Number must be exactly 12 digits"
PAN_ERROR = "PAN must be 10 characters in the format AAAAA9999A"
CREDIT_SCORE_MIN = 300
CREDIT_SCORE_MAX = 900


def submit_to_pipeline(form_data: dict) -> dict:
    try:
        resp = requests.post(API_INGEST_URL, json=form_data, timeout=10)
        return resp.json()
    except Exception as e:
        return {"status": "error", "message": f"Ingestion offline: {e}"}


def format_aadhaar(value) -> str:
    """Restrict Aadhaar input to numeric characters and enforce maxLength=12."""
    return re.sub(r"\D", "", str(value or ""))[:12]


def validate_aadhaar(value) -> bool:
    """True only when value matches ^\\d{12}$ (exactly 12 numeric digits)."""
    return bool(AADHAAR_PATTERN.match(str(value or "")))


def format_pan(value) -> str:
    """Strip non-alphanumerics, upper-case and enforce maxLength=10 for PAN."""
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()[:10]


def validate_pan(value) -> bool:
    return bool(PAN_PATTERN.match(str(value or "")))


def format_credit_score(score) -> str:
    """Render bureau credit_score (300-900) or an N/A placeholder."""
    try:
        s = int(score)
    except (TypeError, ValueError):
        return "N/A"
    if CREDIT_SCORE_MIN <= s <= CREDIT_SCORE_MAX:
        return str(s)
    return "N/A"


def extract_credit_score(result) -> object:
    """Pull credit_score out of a bureau/pipeline response payload if present."""
    if not isinstance(result, dict):
        return None
    if result.get("credit_score") is not None:
        return result.get("credit_score")
    for key in ("data", "bureau_response", "bureau"):
        nested = result.get(key)
        if isinstance(nested, dict) and nested.get("credit_score") is not None:
            return nested.get("credit_score")
    return None


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Customer KYC Registration", layout="centered")
st.title("Customer KYC Registration")
st.caption("Complete the customer KYC details below. Fields marked * are mandatory.")

if "credit_score" not in st.session_state:
    st.session_state["credit_score"] = None
if "last_result" not in st.session_state:
    st.session_state["last_result"] = None

with st.form("kyc_form"):
    st.subheader("Customer Details")
    full_name = st.text_input("Full Name *", max_chars=100, placeholder="As per PAN card")
    email = st.text_input("Email", placeholder="name@example.com")
    mobile_raw = st.text_input("Mobile Number", max_chars=10, placeholder="10-digit mobile")
    dob = st.date_input("Date of Birth")

    st.subheader("Identity Documents")
    pan_raw = st.text_input(
        "PAN *",
        max_chars=10,
        placeholder="ABCDE1234F",
        help="Format: 5 letters, 4 digits, 1 letter",
    )
    aadhaar_raw = st.text_input(
        "Aadhaar Number *",
        key="aadhaar_no",
        max_chars=12,
        placeholder="Exactly 12 numeric digits",
        help="Numeric characters only. Must match ^\\d{12}$",
    )
    # Inline hint mirroring the real-time rule (form re-validates on submit)
    aadhaar_preview = format_aadhaar(aadhaar_raw)
    if aadhaar_raw and not validate_aadhaar(aadhaar_preview):
        st.markdown(f":red[{AADHAAR_ERROR}]")

    st.subheader("Bureau Data")
    st.text_input(
        "Calculated Credit Score",
        value=format_credit_score(st.session_state["credit_score"]),
        disabled=True,
        help="Read-only. Populated from bureau response field credit_score (300-900).",
    )

    submitted = st.form_submit_button("Submit KYC", type="primary")

if submitted:
    aadhaar_no = format_aadhaar(aadhaar_raw)
    pan_no = format_pan(pan_raw)
    mobile = re.sub(r"\D", "", mobile_raw or "")[:10]

    errors = []
    if not (full_name or "").strip():
        errors.append("Full Name is required")
    if not validate_pan(pan_no):
        errors.append(PAN_ERROR)
    if not validate_aadhaar(aadhaar_no):
        errors.append(AADHAAR_ERROR)
    if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        errors.append("Email address is not valid")
    if mobile and not re.match(r"^\d{10}$", mobile):
        errors.append("Mobile Number must be exactly 10 digits")

    if errors:
        # Block submission until all validations pass
        for err in errors:
            st.error(err)
    else:
        form_data = {
            "form": "customer_kyc",
            "full_name": full_name.strip(),
            "email": email.strip(),
            "mobile": mobile,
            "dob": dob.isoformat() if dob else None,
            "pan_no": pan_no,
            "aadhaar_no": aadhaar_no,
        }
        with st.spinner("Submitting KYC to ingestion pipeline..."):
            result = submit_to_pipeline(form_data)

        if not isinstance(result, dict):
            result = {"status": "error", "message": f"Unexpected response: {result}"}

        st.session_state["last_result"] = result
        score = extract_credit_score(result)
        if score is not None:
            st.session_state["credit_score"] = score

        status = str(result.get("status", "")).lower()
        message = result.get("message", "")

        if status == "success":
            st.success(f"KYC submitted successfully. {message}".strip())
        elif status == "requires_pipeline":
            st.info(f"KYC accepted and queued for pipeline processing. {message}".strip())
        elif status == "requires_human_review":
            st.warning(f"KYC submitted but requires human review. {message}".strip())
        elif status == "error":
            st.error(f"Submission failed: {message}")
        else:
            st.info(f"Pipeline response: {json.dumps(result)}")

        st.metric("Calculated Credit Score", format_credit_score(st.session_state["credit_score"]))

        with st.expander("Submitted payload & raw pipeline response"):
            st.json({"request": form_data, "response": result})
