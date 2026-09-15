from core.state import ProjectState
from agents.agent_03_etl.step_01_jira_fetcher import fetch_jira_etl_details
from agents.agent_03_etl.step_02_pipeline_builder import generate_etl_pipeline
from agents.agent_03_etl.step_03_runner import run_etl_in_duckdb

def run_etl_agent(state: ProjectState, raw_payloads: list[dict] = None) -> ProjectState:
    """Agent 03 Orchestrator: Dynamically processes incoming payloads based on Jira spec."""
    if not state.jira_etl_issue_key:
        print("No ETL Jira issue key in state. Skipping Agent 03.")
        return state

    print(f"--- Running Agent 03 (ETL) for Jira Task: {state.jira_etl_issue_key} ---")
    
    # 1. Fetch requirements
    jira_spec = fetch_jira_etl_details(state.jira_etl_issue_key)
    
    # 2. Build dynamic ETL transformation logic
    print("Generating dynamic ETL transformation script via LLM...")
    state.etl_code = generate_etl_pipeline(jira_spec)
    
    # 3. Resolve dynamic payloads from parameters or central state contract
    input_payloads = raw_payloads or getattr(state, "raw_payloads", [])
    
    if not input_payloads:
        print("Warning: No raw payloads passed in state or argument. Skipping batch execution.")
        return state

    # 4. Execute runner dynamically against DuckDB
    print(f"Executing ETL runner against DuckDB staging layer for {len(input_payloads)} record(s)...")
    result = run_etl_in_duckdb(state.etl_code, input_payloads)
    
    print(f"Agent 03 completed successfully. Records processed: {result['processed_count']}")
    return state