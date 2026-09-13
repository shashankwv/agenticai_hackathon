from agents.agent_01_requirements.step_01_confluence_reader import fetch_confluence_page
from agents.agent_01_requirements.step_02_jira_splitter import (
    split_requirement_into_jira_tasks,
)
from agents.agent_01_requirements.step_03_create_jira_issue import (
    create_jira_issue,
)
from core.state import ProjectState


def run_requirements_agent(state: ProjectState, page_id: str = None, project_key: str = "KAN") -> ProjectState:
    """Agent 01: Fetches requirements, splits into tasks, and creates live Jira tickets."""
    # Step 1: Read Confluence page
    confluence_content = fetch_confluence_page(page_id)
    state.raw_confluence_doc = confluence_content

    # Step 2: Split requirement into Jira task descriptions
    jira_breakdown = split_requirement_into_jira_tasks(confluence_content)
    state.jira_ui_task = jira_breakdown.ui_task_description
    state.jira_etl_task = jira_breakdown.etl_task_description
    state.jira_mdm_task = jira_breakdown.mdm_task_description

    # Step 3: Push tasks to Jira and save issue keys back to state
    state = create_jira_issue(state, project_key=project_key)

    return state