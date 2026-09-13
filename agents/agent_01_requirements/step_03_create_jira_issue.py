# agents/agent_01_requirements/step_03_create_jira_issue.py
import os
import requests
from requests.auth import HTTPBasicAuth
from core.state import ProjectState

def _send_single_issue(summary: str, description: str, project_key: str = "CBC3"):
    url = f"{os.getenv('ATLASSIAN_URL')}/rest/api/3/issue"
    auth = HTTPBasicAuth(os.getenv("ATLASSIAN_EMAIL"), os.getenv("ATLASSIAN_API_TOKEN"))
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    
    payload = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}]
            },
            "issuetype": {"name": "Task"}
        }
    }
    
    res = requests.post(url, json=payload, auth=auth, headers=headers)
    if res.status_code == 201:
        key = res.json().get('key')
        print(f"Successfully created Jira Issue: {key}")
        return key
    print(f"Failed to create Jira issue: {res.status_code} - {res.text}")
    return None

def create_jira_issue(state: ProjectState, project_key: str = "CBC3") -> ProjectState:
    if state.jira_ui_task:
        state.jira_ui_issue_key = _send_single_issue("UI Task: Customer KYC Updates", state.jira_ui_task, project_key)
    if state.jira_etl_task:
        state.jira_etl_issue_key = _send_single_issue("ETL Task: Data Ingestion & Risk Indexing", state.jira_etl_task, project_key)
    if state.jira_mdm_task:
        state.jira_mdm_issue_key = _send_single_issue("MDM Task: Master Schema Governance", state.jira_mdm_task, project_key)
    return state