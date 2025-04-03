from google import genai
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
    """Submits the prompt to Gemini 2.0 Flash and returns the response as a string."""
    try:
        api_secret_key = get_gemini_api_key()
        client = genai.Client(api_key=api_secret_key)
        response = client.models.generate_content(model="gemini-2.0-flash", contents=prompt)
        return response.text
    except Exception as e:
        append_to_log('flask_logs', 'GEMINI_INTEGRATION', 'ERROR', 'Exception thrown in submit_prompt_to_gemini: ' + repr(e))
        return ''