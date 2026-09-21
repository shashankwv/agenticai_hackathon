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
# Regex helpers for KYC identifiers and contact numbers
# ---------------------------------------------------------------------------
AADHAAR_RE = re.compile(r"^\d{12}$")
PAN_RE = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
MOBILE_RE = re.compile(r"^[6-9]\d{9}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_aadhaar(value: str) -> str:
    """Strip everything except digits."""
    return re.sub(r"\D", "", value or "")


def format_aadhaar(value: str) -> str:
    """Render Aadhaar as XXXX XXXX XXXX."""
    digits = normalize_aadhaar(value)
    return " ".join(digits[i:i + 4] for i in range(0, len(digits), 4))


def mask_aadhaar(value: str) -> str:
    digits = normalize_aadhaar(value)
    if len(digits) != 12:
        return digits
    return "XXXX XXXX " + digits[-4:]


def normalize_pan(value: str) -> str:
    """Uppercase and strip spaces / punctuation from PAN."""
    return re.sub(r"[^A-Za-z0-9]", "", value or "").upper()


def normalize_mobile(value: str) -> str:
    """Remove spaces, dashes, brackets and a leading +91 / 0 prefix."""
    cleaned = re.sub(r"[\s\-\(\)]", "", value or "")
    cleaned = re.sub(r"^(\+91|91|0)(?=\d{10}$)", "", cleaned)
    return cleaned


def validate_mobile(raw: str, label: str, required: bool):
    """Return (normalized_value, error_message_or_None)."""
    if not raw or not raw.strip():
        if required:
            return "", f"{label} is required."
        return "", None
    value = normalize_mobile(raw)
    if not value.isdigit():
        return value, f"{label} must contain digits only."
    if len(value) != 10:
        return value, f"{label} must be exactly 10 digits (got {len(value)})."
    if not MOBILE_RE.match(value):
        return value, f"{label} is not a valid Indian mobile number (must start with 6-9)."
    return value, None


# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(page_title="Customer KYC Updates", page_icon="🪪", layout="wide")
st.title("🪪 Customer KYC Updates")
st.caption("Onboarding / Profile Update form with optional Alternate Contact Number")

if "customer_profile" not in st.session_state:
    st.session_state["customer_profile"] = None
if "last_response" not in st.session_state:
    st.session_state["last_response"] = None

form_col, view_col = st.columns([3, 2])

# ---------------------------------------------------------------------------
# KYC form
# ---------------------------------------------------------------------------
with form_col:
    with st.form("kyc_form", clear_on_submit=False):
        st.subheader("Customer Details")

        c1, c2 = st.columns(2)
        with c1:
            channel = st.selectbox(
                "Channel",
                ["Internet Banking", "Mobile App", "Branch/CSR"],
                help="Origin screen for this KYC update",
            )
        with c2:
            operation = st.radio(
                "Operation", ["Create (Onboarding)", "Update (Profile)"], horizontal=True
            )

        customer_id = st.text_input(
            "Customer ID",
            placeholder="Leave blank for new onboarding",
            help="Existing CIF / Customer ID for profile updates",
        )

        n1, n2 = st.columns(2)
        with n1:
            first_name = st.text_input("First Name *")
        with n2:
            last_name = st.text_input("Last Name *")

        d1, d2 = st.columns(2)
        with d1:
            dob = st.date_input("Date of Birth *", value=None, format="DD/MM/YYYY")
        with d2:
            email = st.text_input("Email", placeholder="name@example.com")
        email_err = st.empty()

        st.markdown("**Contact Numbers**")
        p1, p2 = st.columns(2)
        with p1:
            primary_contact = st.text_input(
                "Primary Contact Number *",
                max_chars=15,
                placeholder="10-digit mobile number",
            )
            primary_err = st.empty()
        with p2:
            alternate_contact = st.text_input(
                "Alternate Contact Number (optional)",
                max_chars=15,
                placeholder="10-digit mobile number",
                help="Optional. Numeric only, 10 digits, must differ from Primary Contact Number.",
            )
            alternate_err = st.empty()

        st.markdown("**Identity Documents**")
        i1, i2 = st.columns(2)
        with i1:
            aadhaar = st.text_input(
                "Aadhaar Number *",
                max_chars=14,
                placeholder="XXXX XXXX XXXX",
                help="12 digits; spaces are formatted automatically",
            )
            aadhaar_err = st.empty()
        with i2:
            pan = st.text_input(
                "PAN *",
                max_chars=10,
                placeholder="ABCDE1234F",
                help="Format: 5 letters, 4 digits, 1 letter",
            )
            pan_err = st.empty()

        address = st.text_area("Communication Address", height=90)
        address_err = st.empty()

        consent = st.checkbox("Customer has provided consent for KYC data processing *")
        consent_err = st.empty()

        submitted = st.form_submit_button("💾 Save KYC Details", use_container_width=True)

    # -----------------------------------------------------------------------
    # Client-side validation (runs on submit, renders inline errors)
    # -----------------------------------------------------------------------
    if submitted:
        errors = {}

        if not first_name.strip():
            errors["first_name"] = "First Name is required."
        if not last_name.strip():
            errors["last_name"] = "Last Name is required."
        if dob is None:
            errors["dob"] = "Date of Birth is required."

        if email.strip() and not EMAIL_RE.match(email.strip()):
            errors["email"] = "Enter a valid email address."

        primary_norm, p_err = validate_mobile(primary_contact, "Primary Contact Number", required=True)
        if p_err:
            errors["primary_contact"] = p_err

        alternate_norm, a_err = validate_mobile(alternate_contact, "Alternate Contact Number", required=False)
        if a_err:
            errors["alternate_contact"] = a_err
        elif alternate_norm and primary_norm and alternate_norm == primary_norm:
            errors["alternate_contact"] = "Alternate Contact Number must not be the same as Primary Contact Number."

        aadhaar_norm = normalize_aadhaar(aadhaar)
        if not aadhaar_norm:
            errors["aadhaar"] = "Aadhaar Number is required."
        elif not AADHAAR_RE.match(aadhaar_norm):
            errors["aadhaar"] = "Aadhaar must be exactly 12 digits."

        pan_norm = normalize_pan(pan)
        if not pan_norm:
            errors["pan"] = "PAN is required."
        elif not PAN_RE.match(pan_norm):
            errors["pan"] = "PAN must match format ABCDE1234F."

        if not consent:
            errors["consent"] = "Consent is required before saving KYC details."

        # Render inline errors next to the offending fields
        if "email" in errors:
            email_err.error(errors["email"])
        if "primary_contact" in errors:
            primary_err.error(errors["primary_contact"])
        if "alternate_contact" in errors:
            alternate_err.error(errors["alternate_contact"])
        if "aadhaar" in errors:
            aadhaar_err.error(errors["aadhaar"])
        if "pan" in errors:
            pan_err.error(errors["pan"])
        if "consent" in errors:
            consent_err.error(errors["consent"])

        if errors:
            st.error(f"Please fix {len(errors)} validation error(s) before submitting.")
            for field, msg in errors.items():
                if field in ("first_name", "last_name", "dob"):
                    st.write(f"- {msg}")
        else:
            form_data = {
                "task": "customer_kyc_update",
                "channel": channel,
                "operation": "create" if operation.startswith("Create") else "update",
                "customer": {
                    "customer_id": customer_id.strip() or None,
                    "first_name": first_name.strip(),
                    "last_name": last_name.strip(),
                    "date_of_birth": dob.isoformat() if dob else None,
                    "email": email.strip() or None,
                    "primary_contact_number": primary_norm,
                    "alternate_contact_number": alternate_norm or None,
                    "aadhaar_number": aadhaar_norm,
                    "aadhaar_formatted": format_aadhaar(aadhaar_norm),
                    "pan": pan_norm,
                    "address": address.strip() or None,
                    "consent": bool(consent),
                },
            }

            with st.spinner("Submitting KYC details to pipeline..."):
                result = submit_to_pipeline(form_data)

            st.session_state["last_response"] = result
            status = (result or {}).get("status", "")
            message = (result or {}).get("message", "")

            if status == "success":
                st.session_state["customer_profile"] = form_data["customer"]
                st.success(message or "KYC details saved successfully. Profile updated.")
            elif status == "requires_pipeline":
                st.session_state["customer_profile"] = form_data["customer"]
                st.info(message or "Submission accepted and queued for downstream pipeline processing.")
            elif status == "requires_human_review":
                st.session_state["customer_profile"] = form_data["customer"]
                st.warning(message or "Submission requires human review before the profile is finalized.")
            elif status == "error":
                st.error(message or "An error occurred while submitting KYC details.")
            else:
                st.warning(f"Unexpected response from pipeline: {json.dumps(result)}")

            with st.expander("Request payload"):
                st.code(json.dumps(form_data, indent=2), language="json")
            with st.expander("Pipeline response"):
                st.code(json.dumps(result, indent=2, default=str), language="json")

# ---------------------------------------------------------------------------
# Customer Profile view (shows persisted values after save)
# ---------------------------------------------------------------------------
with view_col:
    st.subheader("👤 Customer Profile")
    profile = st.session_state.get("customer_profile")
    if not profile:
        st.info("No profile saved yet. Submit the form to view the customer profile.")
    else:
        full_name = f"{profile.get('first_name', '')} {profile.get('last_name', '')}".strip()
        st.markdown(f"**Name:** {full_name}")
        st.markdown(f"**Customer ID:** {profile.get('customer_id') or '— (new customer)'}")
        st.markdown(f"**Date of Birth:** {profile.get('date_of_birth') or '—'}")
        st.markdown(f"**Email:** {profile.get('email') or '—'}")
        st.divider()
        st.markdown(f"**Primary Contact Number:** {profile.get('primary_contact_number') or '—'}")
        st.markdown(f"**Alternate Contact Number:** {profile.get('alternate_contact_number') or '—'}")
        st.divider()
        st.markdown(f"**Aadhaar:** {mask_aadhaar(profile.get('aadhaar_number', ''))}")
        st.markdown(f"**PAN:** {profile.get('pan') or '—'}")
        st.markdown(f"**Address:** {profile.get('address') or '—'}")
        st.markdown(f"**Consent:** {'Yes' if profile.get('consent') else 'No'}")

        if st.button("🗑️ Clear saved profile"):
            st.session_state["customer_profile"] = None
            st.session_state["last_response"] = None
            st.rerun()
