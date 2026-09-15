from pydantic import BaseModel, Field
# Import your centralized LLM initializer (adjust import path if needed)
from core.llm_factory import get_llm

class ETLPipelineResponse(BaseModel):
    etl_code: str = Field(
        description=(
            "Valid Python script containing transformations using DuckDB/Polars/Pandas. "
            "It must clean raw payloads, enforce string stripping, calculate risk metrics, "
            "and include an explicit function `mask_aadhaar(aadhaar_str)` that masks the middle 8 digits "
            "(e.g., returning 'XXXX-XXXX-1234'). Do NOT include markdown code fences (```)."
        )
    )

def generate_etl_pipeline(jira_spec: str) -> str:
    """Generates Python ETL transformation script based on Jira ticket specifications."""
    base_llm = get_llm()
    structured_llm = base_llm.with_structured_output(ETLPipelineResponse)

    prompt = f"""You are an enterprise ETL Data Engineer.
Based on the following Jira task description, write modular Python transformation logic:

{jira_spec}

Requirements:
1. Parse and sanitize raw incoming customer records.
2. Implement a masking helper `mask_aadhaar(val)` that keeps only the last 4 digits (e.g., 'XXXX-XXXX-1234').
3. Calculate a preliminary `risk_index` float/int using income and credit metrics if present.
4. Provide a core function `transform_batch(raw_records: list) -> list` that outputs cleansed dicts.
Return ONLY valid Python code inside the structured schema field."""

    response: ETLPipelineResponse = structured_llm.invoke(prompt)
    return response.etl_code