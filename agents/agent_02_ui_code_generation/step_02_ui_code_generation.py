import os
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from core.llm_factory import get_llm  # Centralized LLM factory with fallbacks


# ---------------------------------------------------------------------------
# 1. STRUCTURED OUTPUT SCHEMA
# ---------------------------------------------------------------------------
class StreamlitUICodeResponse(BaseModel):
    code: str = Field(
        description=(
            "The raw, valid Python Streamlit code. Do NOT include markdown code"
            " fences (```), backticks, or conversational commentary."
        )
    )


# ---------------------------------------------------------------------------
# 2. SHARED DESIGN SYSTEM CSS (HIGH-CONTRAST ENFORCED)
# ---------------------------------------------------------------------------
DESIGN_SYSTEM_CSS = """
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
"""


# ---------------------------------------------------------------------------
# 3. MAIN UI CODE GENERATION FUNCTION
# ---------------------------------------------------------------------------
def generate_ui_code(ui_details: str, existing_ui_code: str = None) -> str:
    """Generates or updates production-grade Streamlit UI code based on Jira specs."""
    base_llm = get_llm()
    structured_llm = base_llm.with_structured_output(StreamlitUICodeResponse)

    system_prompt = f"""
You are an expert Enterprise Python Streamlit UI engineer.
Generate sleek, production-ready Streamlit code based on the provided requirements.

SYSTEM & UI GUIDELINES:
1. DIRECT ETL INTEGRATION: Do NOT use REST APIs or HTTP fetch requests.
   Import and trigger the DuckDB storage function directly upon form submission:
   `from etl_pipeline import process_and_store_kyc`
2. FORM SUBMISSION & ETL FEEDBACK RULE:
   On form submission, call `res = process_and_store_kyc(formData)`.
   - If `res['status'] == 'success'`, display `st.success(res['message'])`.
   - If `res['status'] == 'warning'`, display `st.warning(res['message'])`.
3. LAYOUT CONTINUITY & DYNAMIC GRIDS: Organize inputs cleanly using `st.form`.
   Group inputs into dynamic multi-column tuples using `st.columns(2)` or `st.columns(3)`.
4. INCREMENTAL SCHEMAS: If existing code is provided, update it incrementally.
   Add new requested fields and remove deleted ones while preserving styling,
   input key names, state logic, and visual structure.
5. VALIDATION & FEEDBACK: Implement real-time regex checks for sensitive inputs (e.g., Aadhaar 12 digits)
   and render clear `st.error()` messages if invalid.
6. DESIGN SYSTEM STYLING: Always embed the standardized high-contrast CSS wrapper at the top:
   `st.markdown('''{DESIGN_SYSTEM_CSS}''', unsafe_allow_html=True)`
7. COMPONENT EXPORT: Provide pure, directly executable Streamlit Python code.
"""

    context_prefix = ""
    if existing_ui_code and existing_ui_code.strip():
        context_prefix = (
            "====================================================================\n"
            "PREVIOUS UI CODE / FEEDBACK CONTEXT:\n"
            "====================================================================\n"
            f"{existing_ui_code}\n\n"
            "INSTRUCTIONS FOR UPDATES:\n"
            "- Modify the code above to fulfill the new specification or fix"
            " compilation/contrast errors.\n"
            "- Maintain high-contrast CSS and dark theme formatting.\n"
            "====================================================================\n\n"
        )

    human_prompt = f"{context_prefix}NEW JIRA SPECIFICATION:\n{ui_details}"

    response: StreamlitUICodeResponse = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt),
    ])

    return response.code