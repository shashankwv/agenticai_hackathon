import os
import requests
from requests.auth import HTTPBasicAuth

def fetch_mdm_jira_issue(issue_key: str) -> str:
    """Fetches MDM task details from Jira REST API by issue key."""
    if not issue_key:
        return ""

    atlassian_url = os.getenv("ATLASSIAN_URL", "https://shashankwv.atlassian.net")
    url = f"{atlassian_url}/rest/api/3/issue/{issue_key}"
    
    auth = HTTPBasicAuth(
        os.getenv("ATLASSIAN_EMAIL", ""),
        os.getenv("ATLASSIAN_API_TOKEN", "")
    )
    headers = {"Accept": "application/json"}

    try:
        response = requests.get(url, auth=auth, headers=headers, timeout=10)
        if response.status_code != 200:
            print(f"Warning: Could not fetch Jira issue {issue_key}. Status: {response.status_code}")
            return ""

        data = response.json()
        summary = data["fields"].get("summary", "")
        
        description_text = ""
        desc_field = data["fields"].get("description")
        if desc_field and "content" in desc_field:
            for block in desc_field["content"]:
                for item in block.get("content", []):
                    if item.get("type") == "text":
                        description_text += item.get("text", "") + "\n"

        return f"Summary: {summary}\nDescription:\n{description_text.strip()}"
    except Exception as e:
        print(f"Failed to fetch Jira MDM issue: {e}")
        return ""