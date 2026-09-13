import os
from pathlib import Path
import requests
from requests.auth import HTTPBasicAuth


def fetch_confluence_page(page_id: str = None) -> str:
  """Fetches business requirements from Confluence or falls back to local markdown."""
  base_url = os.getenv("ATLASSIAN_URL")
  email = os.getenv("ATLASSIAN_EMAIL")
  token = os.getenv("ATLASSIAN_API_TOKEN")

  if not all([base_url, email, token]) or not page_id:
    fallback_path = Path("templates/sample_confluence_spec.md")
    if fallback_path.exists():
      return fallback_path.read_text(encoding="utf-8")
    return (
        "Default Requirement: Add aadhaar_no as VARCHAR(12) required field for"
        " KYC."
    )

  url = f"{base_url}/wiki/rest/api/content/{page_id}?expand=body.storage"
  response = requests.get(url, auth=HTTPBasicAuth(email, token))
  if response.status_code == 200:
    return response.json()["body"]["storage"]["value"]
  else:
    raise ConnectionError(f"Failed to fetch Confluence page: {response.text}")