from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from core.llm_factory import get_llm

class UICodeResponse(BaseModel):
    code: str = Field(
        description="The raw, valid React/TypeScript (TSX) component code. Do NOT include markdown code fences (```), backticks, or conversational text."
    )

def generate_ui_code(ui_details: str) -> str:
    base_llm = get_llm()
    structured_llm = base_llm.with_structured_output(UICodeResponse)
    
    # 1. Provide clear requirements in the system message
    system_prompt = (
        "You are an expert React/TypeScript UI engineer. Generate interactive, high-quality TSX components.\n"
        "Follow these structural & UI guidelines:\n"
        "1. Imports & Animations: Use `framer-motion` (`motion`, `AnimatePresence`) for smooth step transitions, toggles, and dynamic updates.\n"
        "2. Multi-Step Form Layout: Structure complex forms into clear progress steps with step indicator headers and dynamic state tracking.\n"
        "3. Security & Masking Interactivity: Support stateful visibility toggles (e.g., eye icons using `lucide-react`) for confidential inputs like Aadhaar or PIN numbers.\n"
        "4. Risk/Metrics Visualization: Build custom visual meters (such as multi-color linear progress bars or risk category badges with refresh triggers) rather than plain text outputs.\n"
        "5. Component Rules: Export a single `default` functional component designed for App.tsx. Include inline Lucide React icons where applicable."
    )

    human_prompt = f"Jira Specification:\n{ui_details}"
    
    # 2. Invoke using SystemMessage and HumanMessage structure
    response: UICodeResponse = structured_llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=human_prompt)
    ])
    
    return response.code