import warnings
import pytest
from dotenv import load_dotenv

# Load environment variables (.env) before agent imports
load_dotenv()

from core.state import ProjectState
from agents.agent_01_requirements import run_requirements_agent
from agents.agent_02_ui import run_ui_agent
from agents.agent_03_etl import run_etl_agent

warnings.filterwarnings("ignore", category=UserWarning)


# ============================================================================
# AGENT 1 TESTS: Requirements Engine
# ============================================================================
@pytest.mark.parametrize(
    "custom_requirement, expected_field",
    [
        ("Add aadhaar_no as VARCHAR(12) required field", "aadhaar_no"),
        ("Add alternate_phone as VARCHAR(20)", "alternate_phone"),
    ],
)
def test_requirements_agent_field_injection(
    custom_requirement, expected_field
):
    # Setup state dynamically per test case
    initial_state = ProjectState(raw_requirement=custom_requirement)

    # Run Agent 01
    updated_state = run_requirements_agent(initial_state)

    # Assertions for Agent 01
    assert updated_state.current_schema is not None
    field_names = [
        attr.name for attr in updated_state.current_schema.attributes
    ]
    assert expected_field in field_names


# ============================================================================
# AGENT 2 TESTS: UI Engine (Streamlit Generation)
# ============================================================================
def test_ui_agent_generation():
    # Setup initial state with a requirement
    initial_state = ProjectState(
        raw_requirement="Add aadhaar_no as VARCHAR(12) required field"
    )

    # Run Agent 01 to populate state.current_schema
    state_with_schema = run_requirements_agent(initial_state)
    assert state_with_schema.current_schema is not None

    # Run Agent 02 to generate UI code
    final_state = run_ui_agent(state_with_schema)

    # Assertions for Agent 02
    assert final_state.ui_code != ""
    assert "import streamlit" in final_state.ui_code
    assert "aadhaar_no" in final_state.ui_code

    

# ============================================================================
# AGENT 3 TESTS: ETL Engine (Data Pipeline Generation)
# ============================================================================
def test_etl_agent_generation():
    # 1. Setup state and populate schema via Agent 01
    initial_state = ProjectState(
        raw_requirement="Add aadhaar_no as VARCHAR(12) required field"
    )
    state_with_schema = run_requirements_agent(initial_state)

    # 2. Run Agent 03
    final_state = run_etl_agent(state_with_schema)

    # 3. Assertions for Agent 03
    assert final_state.etl_code != ""
    assert "def transform_data" in final_state.etl_code
    assert "aadhaar_no" in final_state.etl_code


# ============================================================================
# AGENT 4 TESTS: MDM Engine (SQL DDL & Governance Generation)
# ============================================================================
def test_mdm_agent_generation():
    # 1. Setup state and populate schema via Agent 01
    initial_state = ProjectState(
        raw_requirement="Add aadhaar_no as VARCHAR(12) required field"
    )
    state_with_schema = run_requirements_agent(initial_state)

    # 2. Run Agent 04
    final_state = run_mdm_agent(state_with_schema)

    # 3. Assertions for Agent 04
    assert final_state.mdm_ddl != ""
    assert "CREATE TABLE" in final_state.mdm_ddl
    assert "ON CONFLICT" in final_state.mdm_ddl


# ============================================================================
# DOCUMENTATION GENERATION TESTS
# ============================================================================
def test_docs_generation():
    """Ensures architecture diagram auto-generation runs without errors."""
    try:
        update_arch_docs()
    except Exception as e:
        pytest.fail(f"Architecture documentation script failed: {e}")