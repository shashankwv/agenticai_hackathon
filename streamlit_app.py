import re
import json
import streamlit as st
import requests

API_INGEST_URL = "http://127.0.0.1:8000/api/ingest"
BUREAU_API_URL = "http://127.0.0.1:8000/api/bureau/score"

# Strict validation patterns
AADHAAR_REGEX = re.compile(r"^\d{12}$")
PAN_REGEX = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")
PHONE_REGEX = re.compile(r"^[6-9]\d{9}$")


def submit_to_pipeline(form_data: dict) -> dict:
    try:
        resp = requests.post(API_INGEST_URL, json=form_data, timeout=10)
        return resp.json()
    except Exception as e:
        return {"status": "error", "message": f"Ingestion server offline (Port 8000). Please start api_bridge.py: {e}"}


# ---------------------------------------------------------------------------
# Pure helpers (importable for unit tests)
# ---------------------------------------------------------------------------
def normalize_aadhaar(raw: str) -> str:
    """Strip spaces/hyphens commonly typed in Aadhaar numbers (e.g. '1234 5678 9012')."""
    return re.sub(r"[\s-]", "", raw or "")


def normalize_pan(raw: str) -> str:
    """Remove whitespace and force uppercase for PAN."""
    return re.sub(r"\s", "", raw or "").upper()


def validate_aadhaar(value: str) -> str:
    """Return '' when valid, otherwise a human-readable error message."""
    if not value:
        return "Aadhaar Number is required."
    if not AADHAAR_REGEX.match(value):
        if not value.isdigit():
            return "Aadhaar must contain numeric digits only (0-9)."
        return f"Aadhaar must be exactly 12 digits (you entered {len(value)})."
    return ""


def validate_pan(value: str) -> str:
    if not value:
        return "PAN is required."
    if not PAN_REGEX.match(value):
        return "PAN must match the format AAAAA9999A (5 letters, 4 digits, 1 letter)."
    return ""


def format_aadhaar(value: str) -> str:
    """Render a valid Aadhaar as 'XXXX XXXX XXXX'."""
    if AADHAAR_REGEX.match(value or ""):
        return " ".join(value[i:i + 4] for i in range(0, 12, 4))
    return value or ""


def mask_aadhaar(value: str) -> str:
    if AADHAAR_REGEX.match(value or ""):
        return f"XXXX XXXX {value[-4:]}"
    return value or ""


def extract_credit_score(response: dict):
    """Pull credit score from ingest/bureau response in a tolerant way."""
    if not isinstance(response, dict):
        return None
    for key in ("credit_score", "calculated_credit_score", "score"):
        if response.get(key) is not None:
            return response.get(key)
    nested = response.get("data") or response.get("bureau") or {}
    if isinstance(nested, dict):
        for key in ("credit_score", "calculated_credit_score", "score"):
            if nested.get(key) is not None:
                return nested.get(key)
    return None


def fetch_credit_score(pan: str, aadhaar: str):
    """Query bureau API for the calculated credit score. Returns int or None."""
    try:
        resp = requests.get(BUREAU_API_URL, params={"pan": pan, "aadhaar": aadhaar}, timeout=10)
        return extract_credit_score(resp.json())
    except Exception:
        return None


def render_credit_score(container, score):
    """Read-only display element for 'Calculated Credit Score'."""
    with container.container():
        st.subheader("Calculated Credit Score")
        display_value = "" if score is None else str(score)
        st.text_input(
            "Calculated Credit Score",
            value=display_value,
            disabled=True,
            key=f"credit_score_display_{display_value}",
            help="Read-only. Populated from the bureau API response after submission.",
        )
        if score is None:
            st.caption("Not yet calculated. Submit the KYC form to fetch the score from the bureau.")
        else:
            try:
                numeric = int(score)
                band = "Excellent" if numeric >= 750 else "Good" if numeric >= 700 else "Fair" if numeric >= 650 else "Poor"
                st.metric(label="Bureau Score", value=numeric, delta=band, delta_color="off")
            except (TypeError, ValueError):
                st.metric(label="Bureau Score", value=str(score))


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------
def main():
    st.set_page_config(page_title="Customer KYC Registration", page_icon="🪪", layout="centered")
    st.title("Customer KYC Registration")
    st.caption("All fields are validated client-side before being sent to the ingestion pipeline.")

    if "credit_score" not in st.session_state:
        st.session_state.credit_score = None
    if "last_response" not in st.session_state:
        st.session_state.last_response = None

    # Placeholder so the read-only score can be refreshed in the same run after submit
    score_placeholder = st.empty()
    render_credit_score(score_placeholder, st.session_state.credit_score)

    st.divider()

    with st.form("kyc_form", clear_on_submit=False):
        st.subheader("Customer Details")
        col1, col2 = st.columns(2)
        with col1:
            full_name = st.text_input("Full Name *", max_chars=100, placeholder="As per Aadhaar")
            dob = st.date_input("Date of Birth *", value=None, format="DD/MM/YYYY")
            phone_raw = st.text_input("Mobile Number *", max_chars=10, placeholder="10-digit mobile")
        with col2:
            email = st.text_input("Email", placeholder="name@example.com")
            pan_raw = st.text_input("PAN *", max_chars=10, placeholder="ABCDE1234F", help="Format: AAAAA9999A")
            aadhaar_raw = st.text_input(
                "Aadhaar Number *",
                max_chars=14,
                placeholder="12-digit numeric Aadhaar",
                help="Exactly 12 numeric digits (spaces/hyphens are ignored).",
            )
        address = st.text_area("Residential Address *", max_chars=300)
        consent = st.checkbox("I consent to Aadhaar/PAN verification and credit bureau inquiry *")

        submitted = st.form_submit_button("Submit KYC", type="primary", use_container_width=True)

    if submitted:
        aadhaar = normalize_aadhaar(aadhaar_raw)
        pan = normalize_pan(pan_raw)
        phone = re.sub(r"\D", "", phone_raw or "")

        errors = []

        if not (full_name or "").strip():
            errors.append("Full Name is required.")
        if dob is None:
            errors.append("Date of Birth is required.")
        if not PHONE_REGEX.match(phone):
            errors.append("Mobile Number must be a valid 10-digit Indian mobile number.")
        if email and not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            errors.append("Email address is not valid.")

        pan_error = validate_pan(pan)
        if pan_error:
            errors.append(f"PAN: {pan_error}")

        # Strict Aadhaar validation: ^\d{12}$ — inline error + block submission
        aadhaar_error = validate_aadhaar(aadhaar)
        if aadhaar_error:
            errors.append(f"Aadhaar Number: {aadhaar_error}")

        if not (address or "").strip():
            errors.append("Residential Address is required.")
        if not consent:
            errors.append("Consent is required to proceed.")

        if errors:
            st.error("Submission blocked. Please fix the following:")
            for err in errors:
                st.markdown(f"- ❌ {err}")
        else:
            form_data = {
                "form_type": "customer_kyc",
                "full_name": full_name.strip(),
                "dob": dob.isoformat(),
                "phone": phone,
                "email": (email or "").strip(),
                "pan": pan,
                "aadhaar": aadhaar,
                "aadhaar_formatted": format_aadhaar(aadhaar),
                "address": address.strip(),
                "consent": bool(consent),
            }

            with st.spinner("Submitting to ingestion pipeline..."):
                response = submit_to_pipeline(form_data)

            if not isinstance(response, dict):
                response = {"status": "error", "message": "Unexpected response from ingestion server."}

            status = str(response.get("status", "")).lower()
            message = response.get("message", "")

            # Populate read-only credit score from bureau response
            credit_score = extract_credit_score(response)
            if credit_score is None and status != "error":
                with st.spinner("Fetching credit score from bureau..."):
                    credit_score = fetch_credit_score(pan, aadhaar)
            if credit_score is not None:
                st.session_state.credit_score = credit_score
                render_credit_score(score_placeholder, credit_score)

            st.session_state.last_response = response

            if status == "success":
                st.success(f"KYC submitted successfully for {form_data['full_name']} (Aadhaar {mask_aadhaar(aadhaar)}). {message}".strip())
            elif status == "requires_pipeline":
                st.info(f"Submission accepted and queued for downstream pipeline processing. {message}".strip())
            elif status == "requires_human_review":
                st.warning(f"Submission flagged for human review. {message}".strip())
            elif status == "error":
                st.error(message or "An error occurred while submitting the KYC form.")
            else:
                st.info(f"Response received with status '{status or 'unknown'}'. {message}".strip())

            with st.expander("Submission payload & server response"):
                safe_payload = dict(form_data)
                safe_payload["aadhaar"] = mask_aadhaar(aadhaar)
                safe_payload["aadhaar_formatted"] = mask_aadhaar(aadhaar)
                st.code(json.dumps(safe_payload, indent=2), language="json")
                st.code(json.dumps(response, indent=2, default=str), language="json")


if __name__ == "__main__":
    main()
