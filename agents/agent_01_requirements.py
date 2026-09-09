import json
from pathlib import Path
from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from core.state import EntitySchema, ProjectState

# Resolve project root dynamically (agents/ -> root)
BASE_DIR = Path(__file__).resolve().parent.parent


def run_requirements_agent(state: ProjectState) -> ProjectState:
    # 1. Load baseline seed schema using absolute path relative to project root
    if state.current_schema is None:
        seed_path = BASE_DIR / "templates" / "seed_schema.json"
        with open(seed_path, "r") as f:
            seed_data = json.load(f)
            state.current_schema = EntitySchema(**seed_data)

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0,
    )

    structured_llm = llm.with_structured_output(EntitySchema)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are an expert Enterprise Master Data Management (MDM) Data Architect.\n"
                "Your goal is to adapt and evolve an existing entity JSON schema based on raw incoming business requirements.\n\n"
                "Rules:\n"
                "- Preserve all existing fields unless explicitly requested to drop/modify them.\n"
                "- Append new fields using standard snake_case naming conventions.\n"
                "- Ensure standard SQL/DDL data types (e.g., VARCHAR(50), INT, TIMESTAMP, BOOLEAN).\n"
                "- Set is_required and primary key flags correctly based on context.",
            ),
            (
                "user",
                "Current Entity Schema:\n{current_schema}\n\n"
                "New Requirement:\n{requirement}",
            ),
        ]
    )

    chain = prompt | structured_llm

    updated_schema = chain.invoke(
        {
            "current_schema": state.current_schema.model_dump_json(indent=2),
            "requirement": state.raw_requirement,
        }
    )

    state.current_schema = updated_schema
    return state