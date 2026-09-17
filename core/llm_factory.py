# core/llm_factory.py
import os
from urllib.parse import urlparse

from dotenv import load_dotenv
from google.genai.errors import APIError, ClientError, ServerError
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_google_genai.chat_models import GoogleAPIError, GoogleRateLimitError
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI

load_dotenv()


def get_llm(temperature: float = 0.0, schema=None):
    raw_models = []

    primary_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    groq_key = os.getenv("GROQ_API_KEY")
    openai_key = os.getenv("OPENAI_API_KEY")
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    azure_endpoint = os.getenv("AZURE_AI_FOUNDRY_ENDPOINT")
    azure_key = os.getenv("AZURE_AI_FOUNDRY_KEY")
    azure_deployment = os.getenv("AZURE_MODEL_DEPLOYMENT")

    # -1. Azure AI Foundry (tried first, everywhere, when configured) — uses
    # the Azure AI "model inference" API, which is OpenAI-compatible at
    # <resource-root>/models/chat/completions?api-version=... The endpoint
    # env var is the project-level URL (.../api/projects/<project>); the
    # model inference route lives off the bare resource root instead, so
    # that suffix is stripped here.
    if azure_endpoint and azure_key and azure_deployment:
        parsed = urlparse(azure_endpoint)
        azure_root = f"{parsed.scheme}://{parsed.netloc}"
        raw_models.append(
            ChatOpenAI(
                model=azure_deployment,
                temperature=temperature,
                openai_api_key=azure_key,
                openai_api_base=f"{azure_root}/models",
                default_query={"api-version": os.getenv("AZURE_AI_FOUNDRY_API_VERSION", "2024-05-01-preview")},
                max_tokens=8192,
                timeout=180,
            )
        )

    # 0. OpenRouter (OpenAI-compatible endpoint, tried first if configured)
    if openrouter_key:
        raw_models.append(
            ChatOpenAI(
                model=os.getenv("OPENROUTER_MODEL", "liquid/lfm-2.5-2.6b:free"),
                temperature=temperature,
                openai_api_key=openrouter_key,
                openai_api_base="https://openrouter.ai/api/v1",
                # Free-tier OpenRouter models default to a low completion cap
                # and many silently spend most of it on hidden "reasoning"
                # tokens, truncating longer structured-output responses (e.g.
                # generated Streamlit code) mid-string. Give it real headroom
                # for both reasoning and the actual output.
                max_tokens=8192,
                timeout=180,
            )
        )

    # 1. Primary Model
    if primary_key:
        raw_models.append(
            ChatGoogleGenerativeAI(
                model="gemini-3.6-flash",
                temperature=temperature,
                google_api_key=primary_key,
            )
        )


    if groq_key:
        raw_models.append(
            ChatGroq(
                model="qwen/qwen3.8-27b",
                temperature=temperature,
                # max_tokens=600,  # Caps expected output below 1000 OTPM
                # max_retries=0,   # Instantly triggers fallbacks if rate limited
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


    # 3. Secondary Non-Google Fallback
    if openai_key:
        raw_models.append(
            ChatOpenAI(
                model="gpt-4o-mini",
                temperature=temperature,
                openai_api_key=openai_key,
            )
        )

    # 4. Backup Gemini Models
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
        raise ValueError("No valid API keys found in environment.")

    # Bind schema to every model
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