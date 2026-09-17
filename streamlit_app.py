import re
import json
import streamlit as st
import requests

# The one live, already-verified ingestion pipeline (ETL cleanse -> DuckDB ->
# MDM golden-record upsert). The generated form below submits here over HTTP
# instead of importing a freshly-(re)generated ETL function directly, so it
# reaches the FULL pipeline — including Agent 04/MDM — reliably, using the
# same stable backend contract regardless of what Agent 03 most recently
# generated.
API_INGEST_URL = "http://127.0.0.1:8000/api/ingest"


def submit_to_pipeline(form_data: dict) -> dict:
    """Posts form_data to the ingestion API. Values from Streamlit widgets
    (e.g. `date` from st.date_input, `Decimal`-like numbers) aren't always
    JSON-serializable as-is, and generated form code doesn't reliably
    remember to convert every field correctly — so serialization happens
    here once, centrally, with `default=str` as a catch-all for any type
    json.dumps doesn't natively support."""
    try:
        payload = json.dumps(form_data, default=str)
        resp = requests.post(
            API_INGEST_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            timeout=20,
        )
        return resp.json()
    except Exception as e:
        return {"status": "error", "message": f"Could not reach the ingestion API: {e}"}


st.set_page_config(page_title="KYC Portal", page_icon="🤖", layout="wide")

st.markdown("""
<style>
    /* Dark slate overall app background */
    .stApp {
        background-color: #0f172a !important;
        color: #f8fafc !important;
    }

    /* Form container styling */
    div[data-testid="stForm"] {
        border: 1px solid #334155 !important;
        border-radius: 12px !important;
        background-color: #1e293b !important;
        padding: 24px !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
    }

    /* 1. INPUT FIELD LABELS (Fixes dark grey unreadable labels) */
    .stTextInput label, .stTextArea label, .stSelectbox label,
    .stNumberInput label, .stDateInput label, div[data-testid="stMarkdownContainer"] p {
        color: #e2e8f0 !important;
        font-weight: 600 !important;
        font-size: 0.95rem !important;
    }

    /* 2. ALL INPUT FIELDS (Text, Date, Select, Number, Textarea) */
    div[data-baseweb="input"] input,
    div[data-baseweb="textarea"] textarea,
    div[data-baseweb="select"] div,
    .stTextInput input,
    .stTextArea textarea,
    .stDateInput input,
    .stNumberInput input,
    .stSelectbox div[role="combobox"] {
        background-color: #1e293b !important;
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        border-radius: 8px !important;
        border: 1px solid #475569 !important;
        font-weight: 500 !important;
    }

    /* 3. INPUT FOCUS STATES */
    div[data-baseweb="input"]:focus-within,
    div[data-baseweb="textarea"]:focus-within {
        border-color: #6366f1 !important;
    }

    /* 4. PLACEHOLDER TEXT CONTRAST */
    textarea::placeholder, input::placeholder {
        color: #94a3b8 !important;
        -webkit-text-fill-color: #94a3b8 !important;
    }

    /* 5. PRIMARY SUBMIT BUTTONS */
    div.stButton > button, div[data-testid="stFormSubmitButton"] > button {
        width: 100%;
        background-color: #4f46e5 !important;
        color: #ffffff !important;
        -webkit-text-fill-color: #ffffff !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
        border: none !important;
        padding: 10px 16px !important;
        transition: all 0.2s ease-in-out;
    }

    div.stButton > button:hover, div[data-testid="stFormSubmitButton"] > button:hover {
        background-color: #4338ca !important;
        color: #ffffff !important;
    }
</style>
""", unsafe_allow_html=True)

# ===== BEGIN GENERATED FORM =====
with st.form("kyc_form"):
    aadhaar = st.text_input(label="Aadhaar Number", value="", placeholder="12-digit Aadhaar number")
    if not re.match(r"^\d{12}$", aadhaar):
        st.error("Aadhaar number must be exactly 12 digits.")

    full_name = st.text_input(label="Full Name", value="")
    nominee_name = st.text_input(label="Nominee Name", value="", placeholder="Enter nominee's full name")
    if not re.match(r"^[a-zA-Z\s'-]{2,100}$", nominee_name):
        st.error("Nominee name must be 2-100 characters containing letters, spaces, hyphens, or apostrophes.")

    dob = st.date_input(label="Date of Birth", value=None)
    email = st.text_input(label="Email", value="")

    contact_col1, contact_col2 = st.columns(2)
    with contact_col1:
        phone = st.text_input(label="Phone Number", value="")
    with contact_col2:
        alternate_phone = st.text_input(label="Alternate Contact Number (optional)", value="", placeholder="Enter alternate contact number")

    alternate_phone_valid = True
    if alternate_phone:
        if not re.match(r"^\d+$", alternate_phone):
            alternate_phone_valid = False
            st.error("Alternate Contact Number must contain numeric characters only.")
        elif not re.match(r"^\d{10}$", alternate_phone):
            alternate_phone_valid = False
            st.error("Alternate Contact Number must be exactly 10 digits.")
        elif alternate_phone == phone:
            alternate_phone_valid = False
            st.error("Alternate Contact Number must be different from Primary Contact Number")

    address_line1 = st.text_input(label="Address Line 1", value="")
    address_line2 = st.text_input(label="Address Line 2", value="")
    city = st.text_input(label="City", value="")
    state = st.text_input(label="State", value="")
    pincode = st.text_input(label="Pincode", value="")
    employment_type = st.selectbox(label="Employment Type", options=["Self-employed", "Employee", "Freelancer", "Other"])
    annual_income = st.number_input(label="Annual Income", min_value=0, max_value=10000000)
    credit_score = st.number_input(label="Credit Score", min_value=300, max_value=850)
    terms_accepted = st.checkbox(label="Accept Terms & Conditions", value=False)

    relationship = st.selectbox(label="Relationship", options=["Spouse", "Parent", "Child", "Other"])

    calculated_credit_score = st.text_input(label="Calculated Credit Score", value="", disabled=True)

    submitted = st.form_submit_button("Submit")

if submitted:
    if not alternate_phone_valid:
        st.error("Please correct the Alternate Contact Number before submitting.")
    else:
        form_data = {
            "full_name": full_name,
            "dob": dob,
            "email": email,
            "phone": phone,
            "alternate_contact_number": alternate_phone,
            "address_line1": address_line1,
            "address_line2": address_line2,
            "city": city,
            "state": state,
            "pincode": pincode,
            "employment_type": employment_type,
            "annual_income": annual_income,
            "credit_score": credit_score,
            "terms_accepted": terms_accepted,
            "relationship": relationship,
            "nominee_name": nominee_name,
            "aadhaar_no": aadhaar
        }
        try:
            res = submit_to_pipeline(form_data)
            if res.get("status") == "success":
                st.success(res.get("message", "Submitted successfully."))
                # Read-only profile summary for contact numbers
                summary_col1, summary_col2 = st.columns(2)
                with summary_col1:
                    st.text_input(label="Primary Contact Number", value=phone, disabled=True)
                with summary_col2:
                    alternate_display = alternate_phone
                    if not alternate_display:
                        alternate_display = "\u2014"
                    st.text_input(label="Alternate Contact Number", value=alternate_display, disabled=True)
                # Read-only display for calculated credit score
                calc_credit = res.get("calculated_credit_score")
                if calc_credit is not None:
                    st.text_input(label="Calculated Credit Score", value=str(calc_credit), disabled=True)
            else:
                st.warning(res.get("message", "Submitted, but one stage reported an issue."))
        except Exception as e:
            st.error(f"Could not reach the ingestion API: {e}")
# ===== END GENERATED FORM =====
