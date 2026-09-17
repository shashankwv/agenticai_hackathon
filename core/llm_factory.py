import os
import logging
from dotenv import load_dotenv

# Exception Imports
from google.genai.errors import APIError, ClientError, ServerError
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai.chat_models import GoogleAPIError, GoogleRateLimitError
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI, AzureChatOpenAI

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_llm(temperature: float = 0.0, schema=None):
    raw_models = []

    # Fetch Environment Keys & Configs
    azure_endpoint = os.getenv("AZURE_AI_FOUNDRY_ENDPOINT")
    azure_key = os.getenv("AZURE_AI_FOUNDRY_KEY")
    azure_deployment = os.getenv("AZURE_MODEL_DEPLOYMENT", "claude-fable-5-1")

    primary_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")

    # -------------------------------------------------------------------
    # 1. Primary Model: Azure AI Foundry Deployment (Claude or Azure OpenAI)
    # -------------------------------------------------------------------
    if azure_endpoint and azure_key:
        try:
            # Try Anthropic / Azure AI Foundry Client Integration
            from langchain_azure_ai import AzureAIAnthropicChatModel

            logger.info(f"🤖 Initializing Azure AI Foundry Claude model: {azure_deployment}")
            raw_models.append(
                AzureAIAnthropicChatModel(
                    endpoint=azure_endpoint,
                    credential=azure_key,
                    model=azure_deployment,
                    temperature=temperature,
                )
            )
        except (ImportError, Exception) as e:
            logger.warning(f"⚠️ AzureAIAnthropicChatModel unavailable ({e}). Falling back to AzureChatOpenAI...")
            
            # Fallback to standard AzureChatOpenAI if Azure OpenAI deployment is used
            raw_models.append(
                AzureChatOpenAI(
                    azure_endpoint=azure_endpoint,
                    api_key=azure_key,
                    azure_deployment=azure_deployment,
                    api_version="2024-06-01",
                    temperature=temperature,
                )
            )

    # -------------------------------------------------------------------
    # 2. Secondary Primary: Primary Gemini Model
    # -------------------------------------------------------------------
    if primary_key:
        raw_models.append(
            ChatGoogleGenerativeAI(
                model="gemini-3.6-flash",
                temperature=temperature,
                google_api_key=primary_key,
            )
        )

    # -------------------------------------------------------------------
    # 3. Secondary Fallback: Groq (Fast Inference)
    # -------------------------------------------------------------------
    if groq_key:
        raw_models.append(
            ChatGroq(
                model="qwen/qwen3.8-27b",
                temperature=temperature,
                groq_api_key=groq_key,
            )
        )



    # # 2. Immediate Non-Google Fallback (Bypasses Google API key quota limits)
    # if groq_key:
    #     raw_models.append(
    #         ChatGroq(
    #             model="llama-3.3-70b-specdec",  # or "llama3-70b-8192"
    #             temperature=temperature,
    #             max_tokens=500,  # Prevents output token rate limit errors on Groq
    #             groq_api_key=groq_key,
    #         )
    #     )
    # 4. Tertiary Fallback: OpenAI
    # -------------------------------------------------------------------
    if openai_key:
        raw_models.append(
            ChatOpenAI(
                model="gpt-4o-mini",
                temperature=temperature,
                openai_api_key=openai_key,
            )
        )

    # -------------------------------------------------------------------
    # 5. Backup Gemini Models
    # -------------------------------------------------------------------
    if primary_key:
        raw_models.append(
            ChatGoogleGenerativeAI(
                model="gemini-2.0-flash",
                temperature=temperature,
                google_api_key=primary_key,
            )
        )
        raw_models.append(
            ChatGoogleGenerativeAI(
                model="gemini-1.5-flash",
                temperature=temperature,
                google_api_key=primary_key,
            )
        )

    if not raw_models:
        raise ValueError("❌ No valid API keys found in environment. Please check your .env file.")

    # -------------------------------------------------------------------
    # Bind Schema & Structure Models
    # -------------------------------------------------------------------
    if schema is not None:
        bound_models = [m.with_structured_output(schema) for m in raw_models]
        primary = bound_models[0]
        fallbacks = bound_models[1:]
    else:
        primary = raw_models[0]
        fallbacks = raw_models[1:]

    exceptions_to_catch = (
        GoogleAPIError,
        GoogleRateLimitError,
        ServerError,
        ClientError,
        APIError,
        Exception,
    )

    if fallbacks:
        return primary.with_fallbacks(
            fallbacks, exceptions_to_handle=exceptions_to_catch
        )
    return primary
    # if fallbacks:
    #     llm = primary.with_fallbacks(
    #         fallbacks,
    #         exceptions_to_handle=(sException,)
    #     )

    #     print("\n=== LLM DEBUG ===")
    #     print("Primary:", type(primary).__name__)

    #     for i, fb in enumerate(fallbacks, start=1):
    #         print(f"Fallback {i}:", type(fb).__name__)

    #     print("Returned Type:", type(llm).__name__)
    #     print("=================\n")

    #     return llm
    # return primary