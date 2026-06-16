"""Central config: loads .env and builds LLMs.

Supports two modes:
  1. TrueFoundry gateway (production) — set TFY_GATEWAY_BASE_URL + TFY_API_KEY in .env
  2. Direct Anthropic (development) — set ANTHROPIC_API_KEY in .env

build_llm() picks the right mode automatically based on which env vars are present.
"""
import os
from crewai import LLM
from dotenv import load_dotenv

load_dotenv()

# ── Detect mode ──
_TFY_URL = os.environ.get("TFY_GATEWAY_BASE_URL", "")
_TFY_KEY = os.environ.get("TFY_API_KEY", "")
_ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# TrueFoundry mode: real gateway URL is set (not a placeholder)
_USE_GATEWAY = bool(_TFY_URL and _TFY_KEY and "<" not in _TFY_URL)

if _USE_GATEWAY:
    GATEWAY_BASE_URL = _TFY_URL
    GATEWAY_API_KEY = _TFY_KEY
    GROK_MODEL_ID = os.environ.get("GROK_MODEL_ID", "")
    CLAUDE_MODEL_ID = os.environ.get("CLAUDE_MODEL_ID", "claude-3-5-sonnet-20260319")
    GEMINI_MODEL_ID = os.environ.get("GEMINI_MODEL_ID", "")
    os.environ["OPENAI_API_KEY"] = GATEWAY_API_KEY
    os.environ["OPENAI_API_BASE"] = GATEWAY_BASE_URL
else:
    # Direct Anthropic mode
    GATEWAY_BASE_URL = ""
    GATEWAY_API_KEY = ""
    GROK_MODEL_ID = ""
    CLAUDE_MODEL_ID = "claude-sonnet-4-20250514"
    GEMINI_MODEL_ID = ""


def build_llm(model_id: str | None = None, temperature: float = 0.2) -> LLM:
    """Return a CrewAI LLM.

    In gateway mode: routes through TrueFoundry.
    In direct mode: calls Anthropic API directly via LiteLLM.
    """
    if _USE_GATEWAY:
        mid = model_id or GROK_MODEL_ID
        return LLM(
            model=f"openai/{mid}",
            base_url=GATEWAY_BASE_URL,
            api_base=GATEWAY_BASE_URL,
            api_key=GATEWAY_API_KEY,
            temperature=temperature,
        )

    # Direct Anthropic — no gateway needed
    return LLM(
        model=f"anthropic/{CLAUDE_MODEL_ID}",
        api_key=_ANTHROPIC_KEY,
        temperature=temperature,
    )
