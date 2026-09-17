# agents/agent_04_mdm/step_03_agent.py
from pathlib import Path
from core.state import ProjectState
from agents.agent_04_mdm.step_01_jira_reader import fetch_mdm_jira_issue
from agents.agent_04_mdm.step_02_ddl_generator import (
    fetch_existing_customer_master_schema,
    generate_production_ddl,
)
from agents.agent_04_mdm.step_04_runner import validate_ddl_syntax
from agents.agent_04_mdm.step_05_postgres_executor import execute_mdm_on_postgres

def run_mdm_agent_autonomous(state: ProjectState, sample_record: dict = None, execute_live: bool = False) -> ProjectState:
    """
    Autonomous Agent 04 Orchestrator:
    1. Step 01 & 02: Generate DDL script from requirement context
    2. Step 03: Save output/mdm/schema.sql artifact
    3. Step 04: Dry-run validation via DuckDB parser
    4. Step 05: Live target schema execution via PostgreSQL driver
    """
    print("--- Running Autonomous Agent 04 (MDM Engine) ---")

    jira_spec = ""
    if getattr(state, "jira_mdm_issue_key", None):
        jira_spec = fetch_mdm_jira_issue(state.jira_mdm_issue_key)
    if not jira_spec:
        jira_spec = "Generate production master table schema for customer KYC records with risk scoring."

    sample_payload = sample_record or getattr(state, "sample_cleansed_output", {
        "full_name": "Ananya Sharma",
        "pan_number": "ABCDE1234F",
        "masked_aadhaar": "XXXX-XXXX-1098",
        "monthly_income": 85000.0,
        "credit_score": 765,
        "risk_index": 22.5
    })

    try:
        # Step 02: Code Generation — check the LIVE table's actual current
        # schema first, so a new Jira story extends it (ALTER ADD COLUMN)
        # instead of generating a disconnected, unrelated table from the
        # Jira text alone.
        existing_schema = fetch_existing_customer_master_schema()
        print(
            f"[1/4] Generating production PostgreSQL DDL "
            f"({'extending existing table' if existing_schema else 'creating new table'})..."
        )
        ddl_sql = generate_production_ddl(jira_spec, sample_payload, existing_schema=existing_schema)
        state.mdm_ddl = ddl_sql

        # Step 03: Persistence
        project_root = Path.cwd().parent if Path.cwd().name == "notebooks" else Path.cwd()
        output_dir = project_root / "output" / "mdm"
        output_dir.mkdir(parents=True, exist_ok=True)
        schema_file = output_dir / "schema.sql"
        schema_file.write_text(ddl_sql, encoding="utf-8")
        print(f"[2/4] Persisted schema to: {schema_file.resolve()}")

        # Step 04: Dry-Run Validation Tool
        print("[3/4] Running Step 04 (DuckDB Dry-Run Syntax Validation)...")
        val_result = validate_ddl_syntax(ddl_sql)
        print(f"      Validation: {val_result['status']} | {val_result['message']}")

        # Step 05: Target Database Deployment Tool
        if execute_live:
            print("[4/4] Running Step 05 (Live PostgreSQL Target Execution)...")
            exec_result = execute_mdm_on_postgres(ddl_sql)
            print(f"      Execution: {exec_result['status']} | {exec_result.get('message') or exec_result.get('error')}")

    except Exception as e:
        error_msg = f"Autonomous Agent 04 Error: {str(e)}"
        print(error_msg)
        state.errors.append(error_msg)

    return state