import os
import requests
from requests.auth import HTTPBasicAuth

def fetch_jira_issue_details(issue_key: str) -> str:
    """Fetches task summary and description from Jira REST API by issue key."""
    if not issue_key:
        return ""

    url = f"{os.getenv('ATLASSIAN_URL', 'https://shashankwv.atlassian.net')}/rest/api/3/issue/{issue_key}"
    auth = HTTPBasicAuth(
        os.getenv("ATLASSIAN_EMAIL"),
        os.getenv("ATLASSIAN_API_TOKEN")
    )
    headers = {"Accept": "application/json"}

    response = requests.get(url, auth=auth, headers=headers)
    if response.status_code != 200:
        raise Exception(f"Failed to fetch Jira ticket {issue_key}: {response.status_code} - {response.text}")

    data = response.json()
    summary = data["fields"].get("summary", "")
    
    # Extract plain text from Atlassian Document Format (ADF) description
    description_text = ""
    desc_field = data["fields"].get("description")
    if desc_field and "content" in desc_field:
        for block in desc_field["content"]:
            for content_item in block.get("content", []):
                if content_item.get("type") == "text":
                    description_text += content_item.get("text", "") + "\n"

    return f"Summary: {summary}\nDescription:\n{description_text.strip()}"