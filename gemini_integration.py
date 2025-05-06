# Commented out because this worked previously but at the time of writing there's package conflicts
# between google-generativeai and langchain. Ugh.

# import google.generativeai as genai
# from redis_tools import get_secrets_dict
# from utils import append_to_log

# def submit_prompt_to_gemini(prompt: str) -> str:
#     """Submits the prompt to Gemini 2.0 Flash and returns the response as a string."""
#     try:
#         api_secret_key = get_gemini_api_key()
#         client = genai.Client(api_key=api_secret_key)
#         response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
#         return response.text
#     except Exception as e:
#         append_to_log('flask_logs', 'GEMINI_INTEGRATION', 'ERROR', 'Exception thrown in submit_prompt_to_gemini: ' + repr(e))
#         return ''

import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from redis_tools import get_secrets_dict
from utils import append_to_log


def get_gemini_api_key() -> str:
    try:
        secrets_dict = get_secrets_dict()
        return secrets_dict['secrets']['gemini']['api_key']
    except Exception as e:
        append_to_log('flask_logs', 'GEMINI_INTEGRATION', 'ERROR', 'Exception thrown in get_gemini_api_key: ' + repr(e))
        return ''


def submit_prompt_to_gemini(prompt: str) -> str:
    # Set your Google API key as an environment variable
    # This is the most secure way to handle your API key
    os.environ["GOOGLE_API_KEY"] = get_gemini_api_key()

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        temperature=0,
        max_tokens=None,
        timeout=None,
        max_retries=2
    )

    messages = [
        (
            "system",
            "You are a helpful assistant. Answer the following question to the best of your ability.",
        ),
        (
            "human",
            prompt
        )
    ]
    
    ai_msg = llm.invoke(messages)
    return ai_msg.content