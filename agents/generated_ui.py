import re
import streamlit as st

AADHAAR_REGEX = re.compile(r"^\d{12}$")


def _validate_aadhaar(value: str) -> bool:
    """Return True if the Aadhaar value is exactly 12 numeric digits."""
    return bool(AADHAAR_REGEX.match(value or ""))


def _fetch_credit_score(customer_id: str):
    """Simulate a credit bureau API lookup.

    In production this would call the credit bureau service. Here we
    deterministically derive a score from the customer id so the UI can
    demonstrate the read-only display behavior.
    """
    try:
        seed = sum(ord(ch) for ch in (customer_id or "anon"))
        # Map into a realistic credit-score band (300 - 850).
        score = 300 + (seed % 551)
        return score
    except Exception:
        return None


def render_generated_ui():
    st.title("Customer KYC Registration")
    st.caption("Jira: CBC3-109 — Customer 360 KYC form with Aadhaar input and credit score display.")

    with st.form("kyc_registration_form", clear_on_submit=False):
       姓