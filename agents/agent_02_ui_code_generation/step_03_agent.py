from core.state import ProjectState
from agents.agent_02_ui_code_generation.step_01_jira_reader import fetch_jira_issue_details
from agents.agent_02_ui_code_generation.step_02_ui_code_generation import generate_ui_code

def run_ui_code_generation_agent(state: ProjectState) -> ProjectState:
    """Agent 02 (UI): Reads live UI task from Jira and generates clean React TSX code."""
    if not state.jira_ui_issue_key:
        print("No UI Jira issue key found in state. Skipping UI code generation.")
        return state

    print(f"Fetching Jira details for UI Task: {state.jira_ui_issue_key}...")
    ui_details = fetch_jira_issue_details(state.jira_ui_issue_key)
    
    print("Generating UI Code (React/TypeScript)...")
    # Guaranteed to return pure TSX code regardless of which model in get_llm() handled the request
    state.ui_code = generate_ui_code(ui_details)
    
    return state