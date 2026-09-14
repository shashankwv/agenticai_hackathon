from pydantic import BaseModel, Field
from core.llm_factory import get_llm

class MDMDDLResponse(BaseModel):
    ddl_sql: str = Field(
        description="Production PostgreSQL DDL SQL script containing table DDL, primary keys, audit columns, indexes, and an UPSERT example."
    )

def generate_production_ddl(jira_spec: str, sample_record: dict) -> str:
    """Generates production PostgreSQL DDL based on Jira specifications and dynamic sample data structure."""
    base_llm = get_llm()
    structured_llm = base_llm.with_structured_output(MDMDDLResponse)

    prompt = f"""You are an expert Lead Database Architect specializing in Master Data Management (MDM).

Based on the Jira specification and cleansed sample data payload, generate a production-ready PostgreSQL DDL script:

Jira Specification:
{jira_spec}

Sample Cleansed Data Payload:
{sample_record}

Requirements:
1. Create a production table under `public` schema named `customer_master`.
2. Add standard MDM audit columns:
   - `id UUID DEFAULT gen_random_uuid() PRIMARY KEY`
   - `created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
   - `updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP`
3. Map data types cleanly (e.g., VARCHAR, DOUBLE PRECISION, INT).
4. Include appropriate column constraints (NOT NULL, UNIQUE where appropriate).
5. Include an example `UPSERT` statement using PostgreSQL `ON CONFLICT` logic.
6. Provide inline SQL comments (`--`) explaining schema design decisions.
7. Return raw SQL script only without markdown code fences.
"""

    response: MDMDDLResponse = structured_llm.invoke(prompt)
    return response.ddl_sql.strip()