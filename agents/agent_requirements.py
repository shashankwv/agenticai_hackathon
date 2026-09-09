import json
import os
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from core.state import EntitySchema, ProjectState

# Load environment variables from .env file
load_dotenv()

def run_requirements_agent(state: ProjectState) -> ProjectState:
    """
    Agent 1: Ingests raw requirements, loads baseline seed schema,
    and uses LLM structured output to adapt the EntitySchema contract.
    """
    # Ensure API Key is available
    if not os.getenv("GEMINI_API_KEY"):
        raise ValueError("GEMINI_API_KEY is not set. Please set it in your .env file or environment.")

    # 1. Load baseline seed schema if no schema currently exists in state
    if state.current_schema is None:
        with open("templates/seed_schema.json", "r") as f:
            seed_data = json.load(f)
            state.current_schema = EntitySchema(**seed_data)

    # If no new user requirement was provided, return baseline schema as-is
    if not state.raw_requirement.strip():
        return state

    # 2. Initialize Gemini LLM with structured output binding
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0,
    )
    structured_llm = llm.with_structured_output(EntitySchema)

    # 3. Prompt definition
    prompt = ChatPromptTemplate.from_messages([
        ("system", 
         "You are an expert Enterprise Master Data Management (MDM) Data Architect.\n"
         "Your task is to adapt an existing JSON entity schema based on new user requirements.\n"
         "Rules:\n"
         "1. Preserve existing attributes unless explicitly instructed to modify or remove them.\n"
         "2. Standardize data types using SQL/DDL conventions (e.g., VARCHAR(X), DATE, NUMBER, TIMESTAMP).\n"
         "3. Ensure column naming follows snake_case conventions."),
        ("user", "Current Schema:\n{current_schema}\n\nNew Requirements:\n{requirement}")
    ])

    # 4. Invoke LLM and get validated Pydantic model
    chain = prompt | structured_llm
    updated_schema = chain.invoke({
        "current_schema": state.current_schema.model_dump_json(indent=2),
        "requirement": state.raw_requirement
    })

    # 5. Update and return state
    state.current_schema = updated_schema
    return state