# agents/agent_04_mdm.py
"""
Agent 04: MDM Engine

Generates production-ready DDL (Data Definition Language) SQL scripts,
primary key constraints, and upsert logic directly from ProjectState.
"""

import sys
from pathlib import Path

# Resolve project root
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from core.state import ProjectState
from core.llm_factory import get_llm


def run_mdm_agent(state: ProjectState) -> ProjectState:
    """Reads current_schema from state and populates state.mdm_ddl with SQL DDL."""
    if not state.current_schema:
        state.errors.append("Agent 04 Error: Missing current_schema in ProjectState.")
        return state

    prompt = f"""
    You are an expert Data Engineer and Database Architect specializing in Master Data Management (MDM).
    
    Given the target schema structure:
    {state.current_schema.model_dump_json(indent=2)}

    Generate a complete, production-ready PostgreSQL DDL SQL script (`schema.sql`).

    Requirements:
    1. Create a table named `{state.current_schema.entity_name}`.
    2. Add standard MDM metadata columns: `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`, `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`.
    3. Include appropriate constraints (PRIMARY KEY on primary id, NOT NULL for required attributes).
    4. Provide an `UPSERT` example query using `ON CONFLICT` logic for master record synchronization.
    5. Provide inline SQL comments (`--`) explaining constraints and schema design.
    6. Return ONLY the executable SQL code block without markdown formatting or introductory text.
    """

    try:
        llm = get_llm(temperature=0.1)
        response = llm.invoke(prompt)
        
        # Clean response string
        sql_code = response.content.replace("```sql", "").replace("```", "").strip()
        state.mdm_ddl = sql_code

    except Exception as e:
        state.errors.append(f"Agent 04 Exception: {str(e)}")

    return state