import os
import requests
from requests.auth import HTTPBasicAuth

def fetch_jira_etl_details(issue_key: str) -> str:
    """Fetches summary and description for an ETL Jira issue key."""
    if not issue_key:
        raise ValueError("No Jira issue key provided for ETL task.")

    atlassian_url = os.getenv("ATLASSIAN_URL", "https://shashankwv.atlassian.net").rstrip("/")
    url = f"{atlassian_url}/rest/api/3/issue/{issue_key}"
    
    auth = HTTPBasicAuth(
        os.getenv("ATLASSIAN_EMAIL") or os.getenv("JIRA_EMAIL"),
        os.getenv("ATLASSIAN_API_TOKEN") or os.getenv("JIRA_API_TOKEN")
    )
    headers = {"Accept": "application/json"}

    response = requests.get(url, auth=auth, headers=headers)
    
    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch Jira issue {issue_key}: {response.status_code} - {response.text}")

    data = response.json()
    fields = data.get("fields", {})
    summary = fields.get("summary", "")
    
    # Extract text content from Atlassian Document Format (ADF) description
    description_raw = fields.get("description")
    description_text = ""
    if isinstance(description_raw, dict):
        content_blocks = description_raw.get("content", [])
        for block in content_blocks:
            for item in block.get("content", []):
                if item.get("type") == "text":
                    description_text += item.get("text", "") + " "
    elif isinstance(description_raw, str):
        description_text = description_raw

    return f"Jira Issue: {issue_key}\nSummary: {summary}\nDescription: {description_text.strip()}"