import re
import json
import streamlit as st
import requests

API_INGEST_URL = "http://127.0.0.1:8000/api/ingest"


def submit_to_pipeline(form_data: dict) -> dict:
    try:
        resp = requests.post(API_INGEST_URL, json=form_data, timeout=10)
        return resp.json()
    except Exception as e:
        return {"status": "error", "message": f"Ingestion server offline (Port 8000). Please start api_bridge.py: {e}"}


# ---------------------------------------------------------------------------
# Regex-based display formatting helpers for Indian identifiers.
# NOTE: These are purely cosmetic formatters (spacing / upper-casing) and do
# NOT perform validation, rejection, or masking. Aadhaar / PAN fields are out
# of scope for the KYC Initial Intake form per the BRD, so these helpers are
# only applied if such keys ever appear in the payload (future-proofing).
# ---------------------------------------------------------------------------
AADHAAR_GROUP_RE = re.compile(r"(\d{4})(?=\d)")
NON_ALNUM_RE = re.compile(r"[^A-Za-z0-9]")
NON_DIGIT_RE = re.compile(r"\D")

# Alternate Contact Number validation (client-side, per change request):
# numeric only + standard 10-digit mobile number length.
MOBILE_NUMBER_RE = re.compile(r"^\d{10}$")
NUMERIC_ONLY_RE = re.compile(r"^\d+$")

CHANNELS = ["Internet Banking", "Mobile App", "Branch/CSR Portal"]


def format_aadhaar(value: str) -> str:
    digits = NON_DIGIT_RE.sub("", str(value or ""))
    return AADHAAR_GROUP_RE.sub(r"\1 ", digits).strip()


def format_pan(value: str) -> str:
    return NON_ALNUM_RE.sub("", str(value or "")).upper()


def apply_identifier_formatting(payload: dict) -> dict:
    formatted = dict(payload)
    if "aadhaar" in formatted:
        formatted["aadhaar"] = format_aadhaar(formatted["aadhaar"])
    if "pan" in formatted:
        formatted["pan"] = format_pan(formatted["pan"])
    return formatted


def validate_alternate_contact(alternate: str, primary: int) -> str:
    """Return an inline error message, or empty string if valid.

    The field is optional: a blank value is always accepted.
    """
    alt = (alternate or "").strip()
    if alt == "":
        return ""
    if not NUMERIC_ONLY_RE.match(alt):
        return "Alternate Contact Number must contain digits only (no spaces, +, or dashes)."
    if not MOBILE_NUMBER_RE.match(alt):
        return "Alternate Contact Number must be a standard 10-digit mobile number."
    if primary and alt == str(int(primary)):
        return "Alternate Contact Number must not be the same as the Primary Contact Number."
    return ""


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Customer KYC Updates", page_icon="\U0001F4CB", layout="centered")
st.title("Customer KYC Updates")
st.subheader("KYC Initial Intake")
st.caption(
    "Per BRD, core intake values are captured as entered and posted raw to the ETL ingestion "
    "endpoint. Client-side validation applies only to the optional Alternate Contact Number field."
)

if "customer_profile" not in st.session_state:
    st.session_state["customer_profile"] = None

channel = st.radio("Channel", CHANNELS, horizontal=True, help="Field renders identically on all three channels.")

with st.form("kyc_form"):
    full_name = st.text_input("Full Name")
    phone_number = st.number_input("Phone Number (Primary Contact)", min_value=0, step=1, format="%d", value=0)
    alternate_contact = st.text_input(
        "Alternate Contact Number (optional)",
        max_chars=15,
        placeholder="10-digit mobile number",
        help="Optional. Digits only, 10 digits, and must differ from the Primary Contact Number.",
    )
    alt_error_slot = st.empty()
    ssn = st.text_input("SSN")
    submitted = st.form_submit_button("Submit")

if submitted:
    alt_error = validate_alternate_contact(alternate_contact, int(phone_number))

    if alt_error:
        alt_error_slot.error(alt_error)
        st.error("Please correct the highlighted field and resubmit.")
    else:
        form_data = {
            "channel": channel,
            "full_name": full_name,
            "phone_number": int(phone_number),
            "alternate_contact_number": (alternate_contact or "").strip(),
            "ssn": ssn,
        }
        form_data = apply_identifier_formatting(form_data)

        with st.spinner("Submitting to ingestion pipeline..."):
            result = submit_to_pipeline(form_data)

        status = str(result.get("status", "")).lower() if isinstance(result, dict) else ""
        message = result.get("message", "") if isinstance(result, dict) else str(result)

        if status == "success":
            st.success(message or "KYC intake submitted successfully.")
            st.session_state["customer_profile"] = form_data
        elif status == "requires_pipeline":
            st.info(message or "Submission accepted and queued for downstream pipeline processing.")
            st.session_state["customer_profile"] = form_data
        elif status == "requires_human_review":
            st.warning(message or "Submission received and flagged for human review.")
            st.session_state["customer_profile"] = form_data
        elif status == "error":
            st.error(message or "An error occurred while submitting the KYC intake.")
        else:
            st.info(f"Response received from ingestion endpoint (status: '{status or 'unknown'}').")

        with st.expander("Submitted payload"):
            st.code(json.dumps(form_data, indent=2), language="json")
        with st.expander("Raw endpoint response"):
            st.code(json.dumps(result, indent=2, default=str), language="json")

# ---------------------------------------------------------------------------
# Customer Profile View (read-only)
# ---------------------------------------------------------------------------
profile = st.session_state.get("customer_profile")
if profile:
    st.divider()
    st.subheader("Customer Profile View")
    st.caption(f"Last saved via {profile.get('channel', 'unknown')} channel. All fields are read-only.")
    st.text_input("Full Name", value=str(profile.get("full_name", "")), disabled=True, key="view_full_name")
    st.text_input("Primary Contact Number", value=str(profile.get("phone_number", "")), disabled=True, key="view_phone")
    st.text_input(
        "Alternate Contact Number",
        value=profile.get("alternate_contact_number") or "Not provided",
        disabled=True,
        key="view_alt_contact",
    )
