# agents/agent_03_etl.py
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from core.state import ProjectState
from core.llm_factory import get_llm


def run_etl_agent(state: ProjectState) -> ProjectState:
    """Agent 03: ETL Engine

    Generates data ingestion and transformation logic (Pandas/Python)
    based on the current EntitySchema inside ProjectState.
    """
    if not state.current_schema:
        raise ValueError("Cannot generate ETL pipeline: ProjectState.current_schema is empty.")

    # Replace old llm definition with factory call
    llm = get_llm(temperature=0)
    # llm = ChatGoogleGenerativeAI(
    #     model="gemini-2.5-flash",
    #     temperature=0.0,
    # )

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an expert Data Engineer specializing in Python, Pandas, and ETL data pipelines.\n"
                "Your task is to generate a standalone, executable Python script that accepts incoming raw record dicts/dataframes\n"
                "and transforms, validates, and cleans them to match the target EntitySchema.\n\n"
                "Rules:\n"
                "- Write a function `transform_data(raw_records: list[dict]) -> list[dict]`.\n"
                "- Perform type conversion, basic data cleansing, null checks for required fields, and default assignments.\n"
                "- Include comments explaining field conversions.\n"
                "- Return ONLY executable Python code without markdown code block wrappers.",
            ),
            (
                "user",
                "Target Entity Schema:\n{schema_json}",
            ),
        ]
    )

    chain = prompt | llm

    response = chain.invoke(
        {"schema_json": state.current_schema.model_dump_json(indent=2)}
    )

    etl_script = response.content.strip()
    if etl_script.startswith("```python"):
        etl_script = etl_script[9:]
    if etl_script.startswith("```"):
        etl_script = etl_script[3:]
    if etl_script.endswith("```"):
        etl_script = etl_script[:-3]

    # Assign directly to state.etl_code
    state.etl_code = etl_script.strip()
    return state