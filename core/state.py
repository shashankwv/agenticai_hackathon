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
    raw_requirement: str = ""
    current_schema: Optional[EntitySchema] = None
    ui_code: str = ""
    etl_code: str = ""
    mdm_ddl: str = ""
    errors: List[str] = Field(default_factory=list)