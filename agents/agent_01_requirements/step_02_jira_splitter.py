from core.llm_factory import get_llm
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field


class JiraTaskBreakdown(BaseModel):
  ui_task_description: str = Field(
      description=(
          "Jira ticket description for frontend React/Streamlit modifications"
      )
  )
  etl_task_description: str = Field(
      description=(
          "Jira ticket description for Python/Pandas data pipeline"
          " modifications"
      )
  )
  mdm_task_description: str = Field(
      description=(
          "Jira ticket description for database schema changes and DDL"
          " governance"
      )
  )


def split_requirement_into_jira_tasks(confluence_text: str) -> JiraTaskBreakdown:
  """Uses Gemini to analyze a Confluence spec and output 3 distinct Jira tasks."""
  llm = get_llm(temperature=0.0)

  prompt = ChatPromptTemplate.from_messages([
      (
          "system",
          "You are an expert Enterprise Scrum Master and Product Owner.\n"
          "Analyze the incoming business requirement document and split it into"
          " three separate Jira tasks:\n1. UI Task\n2. ETL Task\n3. MDM Task\n"
          "Return structured output matching the requested model format.",
      ),
      ("user", "Business Requirement Document:\n{confluence_text}"),
  ])

  chain = prompt | llm.with_structured_output(JiraTaskBreakdown)
  return chain.invoke({"confluence_text": confluence_text})