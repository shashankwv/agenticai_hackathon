from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from core.llm_factory import get_llm

class UICodeResponse(BaseModel):
    code: str = Field(
        description="The raw, valid React/TypeScript (TSX) component code. Do NOT include markdown code fences (```), backticks, or conversational text."
    )

def generate_ui_code(ui_details: str) -> str:
    # 1. Fetch your unified LLM instance (which manages fallbacks under the hood)
    base_llm = get_llm()
    
    # 2. Bind the Pydantic schema to force structured JSON output across all fallback models
    structured_llm = base_llm.with_structured_output(UICodeResponse)
    
    # 3. Invoke the structured LLM
    prompt = f"You are an expert React/TypeScript UI engineer. Generate modular, production-grade TSX code based on the following Jira spec:\n\n{ui_details}"
    
    response: UICodeResponse = structured_llm.invoke(prompt)
    
    # 4. Return the pure TSX code string directly
    return response.code