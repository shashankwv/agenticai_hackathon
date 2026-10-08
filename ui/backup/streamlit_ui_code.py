import re
import json
import uuid

import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
API_INGEST_URL = "http://127.0.0.1:8000/api/ingest"

# Regex patterns used for formatting / normalisation of identifiers.
_AADHAAR_PATTERN = re.compile(r"^\d{12}$")                       # 12 digits -> XXXX XXXX XXXX
_PAN_PATTERN = re.compile(r"^[A-Za-z]{5}\d{4}[A-Za-z]$")           # ABCDE1234F -> upper-cased
_SSN_PATTERN = re.compile(r"^\d{9}$")                           # 9 digits  -> XXX-XX-XXXX
_NON_ALNUM = re.compile(r"[^A-Za-z0-9]")
_BLANK = re.compile(r"^\s*$")
_DIGITS_ONLY = re.compile(r"^\d+$")

# Standard mobile number length, configurable per country code.
CONTACT_LENGTH_BY_COUNTRY = {
    "+91 (India)": 10,
    "+1 (USA / Canada)": 10,
    "+44 (United Kingdom)": 10,
    "+61 (Australia)": 9,
    "+971 (UAE)": 9,
    "+65 (Singapore)": 8,
}

# Marital status enum (string values bound to payload key `marital_status`).
MARITAL_STATUS_OPTIONS = ["Single", "Married", "Divorced", "Widowed"]

# i18n labels / accessibility text (English baseline; swap dict for other locales).
LABELS = {
    "title": "Customer KYC - Initial Intake",
    "full_name": "Full Name",
    "country_code": "Country Code",
    "primary_contact": "Primary Contact Number",
    "alternate_contact": "Alternate Contact Number (optional)",
    "alternate_contact_short": "Alternate Contact Number",
    "alternate_help": "Optional. Digits only; must match the standard mobile length for the selected country and must differ from the Primary Contact Number.",
    "primary_help": "Digits only. Transmitted as entered.",
    "ssn": "SSN",
    "aadhaar": "Aadhaar Number",
    "pan": "PAN",
    "marital_status": "Marital Status *",
    "marital_help": "Required. Select exactly one option.",
    "submit": "Submit",
    "err_numeric": "Alternate Contact Number must contain digits only.",
    "err_length": "Alternate Contact Number must be exactly {n} digits for the selected country code.",
    "err_same": "Alternate Contact Number must be different from the Primary Contact Number.",
    "err_marital_required": "Marital Status is required. Please select one option.",
    "err_marital_invalid": "Marital Status must be one of: {opts}.",
    "profile_header": "Customer Profile (read-only)",
    "unmask": "Show unmasked contact numbers",
    "not_provided": "Not provided",
}


# ---------------------------------------------------------------------------
# Formatting helpers (regex based, non-blocking)
# ---------------------------------------------------------------------------
def format_aadhaar(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if _AADHAAR_PATTERN.match(digits):
        return re.sub(r"(\d{4})(\d{4})(\d{4})", r"\1 \2 \3", digits)
    return value


def format_pan(value: str) -> str:
    compact = _NON_ALNUM.sub("", value or "")
    if _PAN_PATTERN.match(compact):
        return compact.upper()
    return value


def format_ssn(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if _SSN_PATTERN.match(digits):
        return re.sub(r"(\d{3})(\d{2})(\d{4})", r"\1-\2-\3", digits)
    return value


def normalize_identifier(value: str) -> str:
    """Apply best-effort regex formatting for SSN / Aadhaar / PAN style identifiers.

    Never raises or rejects: if the value matches no known shape it is returned
    exactly as typed so the raw payload reaches the pipeline untouched.
    """
    if value is None:
        return value
    compact = _NON_ALNUM.sub("", value)
    if _SSN_PATTERN.match(compact):
        return format_ssn(compact)
    if _AADHAAR_PATTERN.match(compact):
        return format_aadhaar(compact)
    if _PAN_PATTERN.match(compact):
        return format_pan(compact)
    return value


# ---------------------------------------------------------------------------
# Contact number helpers (validation + masking)
# ---------------------------------------------------------------------------
def clean_contact(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def validate_alternate_contact(alternate: str, primary: str, expected_len: int) -> list:
    """Client-side rules for the optional Alternate Contact Number.

    - blank is allowed (field is optional)
    - numeric only
    - standard mobile length for the selected country code
    - must not equal the Primary Contact Number
    """
    errors = []
    alt = clean_contact(alternate)
    if not alt:
        return errors
    if not _DIGITS_ONLY.match(alt):
        errors.append(LABELS["err_numeric"])
    elif len(alt) != expected_len:
        errors.append(LABELS["err_length"].format(n=expected_len))
    if alt == clean_contact(primary):
        errors.append(LABELS["err_same"])
    return errors


def validate_marital_status(value) -> list:
    """Required-field rule for Marital Status: must be one of the enum options."""
    errors = []
    if value is None or (isinstance(value, str) and _BLANK.match(value)):
        errors.append(LABELS["err_marital_required"])
    elif value not in MARITAL_STATUS_OPTIONS:
        errors.append(LABELS["err_marital_invalid"].format(opts=", ".join(MARITAL_STATUS_OPTIONS)))
    return errors


def mask_contact(value, unmasked: bool = False) -> str:
    """Masked/unmasked display consistent for primary and alternate numbers; null-safe."""
    text = clean_contact(value)
    if not text:
        return LABELS["not_provided"]
    if unmasked:
        return text
    if len(text) <= 4:
        return "*" * len(text)
    return "*" * (len(text) - 4) + text[-4:]


# ---------------------------------------------------------------------------
# Payload builder (single source of truth for the ETL/API contract)
# ---------------------------------------------------------------------------
def build_payload(full_name, country_code, phone_number, alternate_contact, ssn, aadhaar, pan, marital_status) -> dict:
    alt_clean = clean_contact(alternate_contact)
    return {
        "full_name": full_name,
        "country_code": str(country_code).split(" ")[0],
        "phone_number": clean_contact(phone_number),
        "alternateContactNumber": alt_clean if alt_clean else None,
        "ssn": normalize_identifier(ssn),
        "aadhaar": format_aadhaar(aadhaar),
        "pan": format_pan(pan),
        "marital_status": str(marital_status),
    }


# ---------------------------------------------------------------------------
# API bridge
# ---------------------------------------------------------------------------
def submit_to_pipeline(form_data: dict) -> dict:
    try:
        # Dynamically ensure a unique ID is attached if required by API schema.
        current_id = form_data.get("id")
        if current_id is None or (isinstance(current_id, str) and _BLANK.match(current_id)):
            form_data["id"] = str(uuid.uuid4())
        resp = requests.post(API_INGEST_URL, json=form_data, timeout=10)
        return resp.json()
    except Exception as e:
        return {
            "status": "error",
            "message": f"Ingestion server offline (Port 8000). Please start api_bridge.py: {e}",
        }


# ---------------------------------------------------------------------------
# Lightweight self-tests (required validation + payload inclusion)
# ---------------------------------------------------------------------------
def run_self_tests() -> list:
    results = []

    def check(name, condition):
        results.append((name, bool(condition)))

    # Required validation: no selection blocks submission.
    check("marital_status: None -> required error", validate_marital_status(None) == [LABELS["err_marital_required"]])
    check("marital_status: blank -> required error", validate_marital_status("  ") == [LABELS["err_marital_required"]])
    check("marital_status: invalid enum -> invalid error", len(validate_marital_status("Engaged")) == 1)
    for opt in MARITAL_STATUS_OPTIONS:
        check(f"marital_status: '{opt}' -> valid", validate_marital_status(opt) == [])

    # Payload inclusion: marital_status bound as string enum.
    payload = build_payload("Jane", "+91 (India)", "9876543210", "", "123456789", "123456789012", "abcde1234f", "Married")
    check("payload contains marital_status", "marital_status" in payload)
    check("payload marital_status is string enum", payload["marital_status"] == "Married")
    check("payload serialisable to JSON", isinstance(json.dumps(payload), str))
    check("payload aadhaar formatted", payload["aadhaar"] == "1234 5678 9012")
    check("payload pan upper-cased", payload["pan"] == "ABCDE1234F")
    check("payload alternate null when blank", payload["alternateContactNumber"] is None)
    return results


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
st.set_page_config(page_title="KYC Initial Intake", page_icon="\U0001FAAA", layout="centered")
st.title("\U0001FAAA " + LABELS["title"])
st.caption(
    "Identifiers are forwarded as entered to the intake ingestion endpoint. "
    "The optional Alternate Contact Number and the mandatory Marital Status are validated client-side per BRD."
)

if "last_profile" not in st.session_state:
    st.session_state["last_profile"] = None

with st.form("kyc_form", clear_on_submit=False):
    full_name = st.text_input(LABELS["full_name"], placeholder="e.g. Jane Q. Public")
    country_code = st.selectbox(
        LABELS["country_code"],
        list(CONTACT_LENGTH_BY_COUNTRY.keys()),
        index=0,
        help="Determines the standard mobile number length used for validation.",
    )
    col_primary, col_alternate = st.columns(2)
    with col_primary:
        phone_number = st.text_input(
            LABELS["primary_contact"],
            placeholder="Digits only",
            help=LABELS["primary_help"],
            key="primary_contact_input",
        )
    with col_alternate:
        alternate_contact = st.text_input(
            LABELS["alternate_contact"],
            placeholder="Digits only",
            help=LABELS["alternate_help"],
            key="alternate_contact_input",
        )
    ssn = st.text_input(
        LABELS["ssn"],
        placeholder="e.g. 123-45-6789",
        type="password",
        help="Masked on screen only; value is transmitted as entered.",
    )
    # Mandatory Marital Status radio group: directly after SSN, no default selection.
    marital_status = st.radio(
        LABELS["marital_status"],
        MARITAL_STATUS_OPTIONS,
        index=None,
        horizontal=True,
        help=LABELS["marital_help"],
        key="marital_status_input",
    )
    marital_error_slot = st.empty()
    aadhaar = st.text_input(LABELS["aadhaar"], placeholder="e.g. 1234 5678 9012")
    pan = st.text_input(LABELS["pan"], placeholder="e.g. ABCDE1234F")
    submitted = st.form_submit_button(LABELS["submit"], type="primary", use_container_width=True)

if submitted:
    expected_len = CONTACT_LENGTH_BY_COUNTRY.get(country_code, 10)
    alt_errors = validate_alternate_contact(alternate_contact, phone_number, expected_len)
    marital_errors = validate_marital_status(marital_status)

    if marital_errors:
        # Inline required-field error rendered directly beneath the radio group.
        marital_error_slot.error(marital_errors[0], icon="\U0001F6AB")

    if alt_errors or marital_errors:
        # Submission is blocked until all client-side errors are corrected.
        for err in alt_errors + marital_errors:
            st.error(err, icon="\U0001F6AB")
    else:
        # Payload agreed with ETL team; alternateContactNumber is null when not provided.
        form_data = build_payload(
            full_name, country_code, phone_number, alternate_contact, ssn, aadhaar, pan, marital_status
        )

        with st.spinner("Submitting to intake pipeline..."):
            result = submit_to_pipeline(form_data)

        status = str(result.get("status", "")).lower() if isinstance(result, dict) else ""
        message = result.get("message", "") if isinstance(result, dict) else str(result)

        if status == "success":
            st.toast("KYC record submitted successfully", icon="\u2705")
            st.success(message or f"Record {form_data.get('id')} ingested successfully.")
        elif status == "requires_pipeline":
            st.toast("Record queued for pipeline processing", icon="\u2139\uFE0F")
            st.info(message or f"Record {form_data.get('id')} accepted and queued for pipeline processing.")
        elif status == "requires_human_review":
            st.toast("Record flagged for human review", icon="\u26A0\uFE0F")
            st.warning(message or f"Record {form_data.get('id')} requires human review before ingestion.")
        elif status == "error":
            st.toast("Submission failed", icon="\u274C")
            st.error(message or "An unknown error occurred during ingestion.")
        else:
            st.warning(f"Unexpected response from ingestion endpoint: {json.dumps(result, default=str)}")

        st.session_state["last_profile"] = form_data

        with st.expander("Submitted payload (debug)", expanded=False):
            st.code(json.dumps(form_data, indent=2, default=str), language="json")

# ---------------------------------------------------------------------------
# Read-only profile view
# ---------------------------------------------------------------------------
profile = st.session_state.get("last_profile")
if profile:
    st.divider()
    st.subheader(LABELS["profile_header"])
    unmasked = st.checkbox(LABELS["unmask"], value=False, key="unmask_toggle")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**{LABELS['full_name']}:** {profile.get('full_name') or LABELS['not_provided']}")
        st.markdown(f"**{LABELS['country_code']}:** {profile.get('country_code') or LABELS['not_provided']}")
        st.markdown(f"**{LABELS['primary_contact']}:** {mask_contact(profile.get('phone_number'), unmasked)}")
        st.markdown(
            f"**{LABELS['alternate_contact_short']}:** {mask_contact(profile.get('alternateContactNumber'), unmasked)}"
        )
    with c2:
        st.markdown(f"**Marital Status:** {profile.get('marital_status') or LABELS['not_provided']}")
        st.markdown(f"**{LABELS['aadhaar']}:** {profile.get('aadhaar') or LABELS['not_provided']}")
        st.markdown(f"**{LABELS['pan']}:** {profile.get('pan') or LABELS['not_provided']}")
        st.markdown(f"**Record ID:** {profile.get('id') or LABELS['not_provided']}")

# ---------------------------------------------------------------------------
# Developer self-tests (required validation + payload inclusion)
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("Developer tools")
    if st.button("Run self-tests", use_container_width=True):
        test_results = run_self_tests()
        passed = sum(1 for _, ok in test_results if ok)
        st.write(f"{passed}/{len(test_results)} tests passed")
        for name, ok in test_results:
            st.write(("\u2705 " if ok else "\u274C ") + name)
