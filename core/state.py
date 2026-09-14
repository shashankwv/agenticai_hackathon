from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class AttributeSpec(BaseModel):
    name: str
    data_type: str
    is_required: bool = False
    is_primary_key: bool = False
    description: Optional[str] = None

class EntitySchema(BaseModel):
    domain: str
    entity_name: str
    attributes: List[AttributeSpec]

class ProjectState(BaseModel):
    raw_confluence_doc: str = ""
    jira_ui_task: str = ""
    jira_etl_task: str = ""
    jira_mdm_task: str = ""
    
    # Track created ticket keys
    jira_ui_issue_key: Optional[str] = None
    jira_etl_issue_key: Optional[str] = None
    jira_mdm_issue_key: Optional[str] = None
    
    # Active Dynamic Server & Execution URLs
    ui_sandbox_url: Optional[str] = None
    dynamic_payload_schema: Dict[str, Any] = Field(default_factory=dict)

    # ADD THIS FIELD TO ALLOW DYNAMIC INGESTION PAYLOADS
    raw_payloads: List[Dict[str, Any]] = Field(default_factory=list)
    
    current_schema: Optional[EntitySchema] = None
    ui_code: str = ""
    etl_code: str = ""
    mdm_ddl: str = ""
    errors: List[str] = Field(default_factory=list)