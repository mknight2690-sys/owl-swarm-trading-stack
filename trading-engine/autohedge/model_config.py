"""LLM model selection for AutoHedge agents (OpenRouter free tier)."""

from __future__ import annotations

import os

# Pinned free model — tool-calling verified with LiteLLM + OpenRouter.
# (Router `openrouter/free` also works but litellm flags it as non-tool; use bootstrap patch.)
DEFAULT_MODEL = "openrouter/openai/gpt-oss-120b:free"


def agent_model_name() -> str:
    """Model slug for swarms Agent / LiteLLM."""
    return os.getenv("AUTOHEDGE_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
