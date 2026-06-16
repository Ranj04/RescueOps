"""Central config: loads .env and builds LLMs that route through the TrueFoundry gateway.

build_llm() encodes the gateway wiring once so every agent routes correctly.
See test_crew.py for why api_base AND the OPENAI_* env vars are both needed
(a CrewAI/LiteLLM routing quirk that otherwise 401s against api.openai.com).
"""
import os
from crewai import LLM
from dotenv import load_dotenv

load_dotenv()

GATEWAY_BASE_URL = os.environ["TFY_GATEWAY_BASE_URL"]
GATEWAY_API_KEY = os.environ["TFY_API_KEY"]

GROK_MODEL_ID = os.environ["GROK_MODEL_ID"]
CLAUDE_MODEL_ID = os.environ["CLAUDE_MODEL_ID"]
GEMINI_MODEL_ID = os.environ["GEMINI_MODEL_ID"]

# CrewAI's internal calls can bypass the LLM object and read these instead. Set once.
os.environ["OPENAI_API_KEY"] = GATEWAY_API_KEY
os.environ["OPENAI_API_BASE"] = GATEWAY_BASE_URL


def build_llm(model_id: str = GROK_MODEL_ID, temperature: float = 0.2) -> LLM:
    """Return a CrewAI LLM that routes through the TrueFoundry gateway."""
    return LLM(
        model=f"openai/{model_id}",  # openai/ prefix -> LiteLLM uses the OpenAI-compatible path
        base_url=GATEWAY_BASE_URL,
        api_base=GATEWAY_BASE_URL,   # LiteLLM reads api_base, not base_url
        api_key=GATEWAY_API_KEY,
        temperature=temperature,
    )
