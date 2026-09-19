from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import re
from pydantic import BaseModel, Field
import requests
from requests.auth import HTTPBasicAuth
from langchain_core.prompts import ChatPromptTemplate
from core.llm_factory import get_llm
from core.state import ProjectState

# ==========================================
# Step 1: Confluence Reader with Clean Text Extraction
# ==========================================

def clean_html(raw_html: str) -> str:
    """Strips HTML tags and compresses whitespace to reduce LLM input tokens."""
    clean = re.sub(r"<[^>]+>", " ", raw_html)
    return re.sub(r"\s+", " ", clean).strip()


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
        raw_val = response.json()["body"]["storage"]["value"]
        return clean_html(raw_val)
    else:
        raise ConnectionError(f"Failed to fetch Confluence page: {response.text}")


# ==========================================
# Step 2: Jira Splitter
# ==========================================

class JiraTaskBreakdown(BaseModel):
    ui_task_description: str = Field(
        description="Jira ticket description for frontend React/Streamlit modifications"
    )
    etl_task_description: str = Field(
        description="Jira ticket description for Python/Pandas data pipeline modifications"
    )
    mdm_task_description: str = Field(
        description="Jira ticket description for database schema changes and DDL governance"
    )


def split_requirement_into_jira_tasks(confluence_text: str) -> JiraTaskBreakdown:
    """Uses LLM to analyze a Confluence spec and output 3 distinct Jira tasks."""
    structured_llm = get_llm(temperature=0.0, schema=JiraTaskBreakdown)

    prompt = ChatPromptTemplate.from_messages([
        (
            "system",
            "You are an expert Enterprise Scrum Master.\n"
            "Analyze the business requirement and split it into 3 concise Jira tasks:\n"
            "1. UI Task\n2. ETL Task\n3. MDM Task\n"
            "Keep task descriptions direct, technical, and formatted strictly to the JSON schema.",
        ),
        ("user", "Business Requirement Document:\n{confluence_text}"),
    ])

    chain = prompt | structured_llm
    return chain.invoke({"confluence_text": confluence_text})


# ==========================================
# Step 3: Concurrent Jira Issue Creation
# ==========================================

def _send_single_issue(summary: str, description: str, project_key: str = "CBC3"):
    if not description:
        return None

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
    
    try:
        res = requests.post(url, json=payload, auth=auth, headers=headers, timeout=5)
        if res.status_code == 201:
            key = res.json().get("key")
            print(f"Successfully created Jira Issue: {key}")
            return key
    except Exception as err:
        print(f"Failed to create Jira issue: {err}")
    return None


def create_jira_issues_parallel(state: ProjectState, project_key: str = "CBC3") -> ProjectState:
    """Executes Jira issue creations in parallel threads to avoid network latency bottlenecks."""
    tasks = [
        ("UI Task: Customer KYC Updates", state.jira_ui_task, "jira_ui_issue_key"),
        ("ETL Task: Data Ingestion & Risk Indexing", state.jira_etl_task, "jira_etl_issue_key"),
        ("MDM Task: Master Schema Governance", state.jira_mdm_task, "jira_mdm_issue_key"),
    ]

    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(_send_single_issue, summary, task_desc, project_key): attr_name
            for summary, task_desc, attr_name in tasks if task_desc
        }
        for future in futures:
            attr_name = futures[future]
            setattr(state, attr_name, future.result())

    return state


# ==========================================
# Step 4: Requirements Agent Execution Entrypoint
# ==========================================

def run_requirements_agent(state: ProjectState, page_id: str = None, project_key: str = "KAN") -> ProjectState:
    """Agent 01: Fetches requirements, splits into tasks, and creates live Jira tickets."""
    confluence_content = fetch_confluence_page(page_id)
    state.raw_confluence_doc = confluence_content

    jira_breakdown = split_requirement_into_jira_tasks(confluence_content)
    state.jira_ui_task = jira_breakdown.ui_task_description
    state.jira_etl_task = jira_breakdown.etl_task_description
    state.jira_mdm_task = jira_breakdown.mdm_task_description

    state = create_jira_issues_parallel(state, project_key=project_key)

    return state