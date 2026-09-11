# core/llm_factory.py
import os
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

    # 1. Primary Model
    if primary_key:
        raw_models.append(
            ChatGoogleGenerativeAI(
                model="gemini-2.5-flash",
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
    #         exceptions_to_handle=(Exception,)
    #     )

    #     print("\n=== LLM DEBUG ===")
    #     print("Primary:", type(primary).__name__)

    #     for i, fb in enumerate(fallbacks, start=1):
    #         print(f"Fallback {i}:", type(fb).__name__)

    #     print("Returned Type:", type(llm).__name__)
    #     print("=================\n")

    #     return llm
    # return primary