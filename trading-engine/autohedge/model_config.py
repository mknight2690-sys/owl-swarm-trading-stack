"""LLM model selection for AutoHedge agents (NVIDIA NIM GLM-5.1)."""

from __future__ import annotations

import os

# Pinned model — NVIDIA GLM-5.1 via NIM (tool-calling verified with LiteLLM).
# Override via env: AUTOHEDGE_MODEL=nvidia_nim/z-ai/glm-5.1
DEFAULT_MODEL = "nvidia_nim/z-ai/glm-5.1"


def agent_model_name() -> str:
    """Model slug for swarms Agent / LiteLLM."""
    return os.getenv("AUTOHEDGE_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
