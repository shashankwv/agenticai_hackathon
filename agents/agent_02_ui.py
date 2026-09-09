# agents/agent_02_ui.py
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from core.state import ProjectState


def run_ui_agent(state: ProjectState) -> ProjectState:
    """Agent 02: UI Engine

    Generates an interactive Streamlit application based on the current
    EntitySchema inside ProjectState.
    """
    if not state.current_schema:
        raise ValueError("Cannot generate UI: ProjectState.current_schema is empty.")

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.0,
    )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an expert Frontend Engineer specializing in Streamlit and Python dashboards.\n"
                "Your task is to take a structured entity schema and generate a full, executable Streamlit form.\n\n"
                "Rules:\n"
                "- Create inputs corresponding to each field in the schema (e.g., st.text_input, st.number_input, st.checkbox).\n"
                "- Include form validation and a Submit button.\n"
                "- Return ONLY executable Python code without markdown code block wrappers.",
            ),
            (
                "user",
                "Entity Schema:\n{schema_json}",
            ),
        ]
    )

    chain = prompt | llm

    response = chain.invoke(
        {"schema_json": state.current_schema.model_dump_json(indent=2)}
    )

    ui_script = response.content.strip()
    if ui_script.startswith("```python"):
        ui_script = ui_script[9:]
    if ui_script.startswith("```"):
        ui_script = ui_script[3:]
    if ui_script.endswith("```"):
        ui_script = ui_script[:-3]

    # Assign directly to state.ui_code
    state.ui_code = ui_script.strip()
    return state