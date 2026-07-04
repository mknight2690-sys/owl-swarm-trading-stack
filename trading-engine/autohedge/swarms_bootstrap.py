"""Patches for Swarms + LiteLLM with OpenRouter free reasoning/tool models."""

from __future__ import annotations

import json

from autohedge.handoff_pipeline import ordered_handoff_task
import litellm.utils as litellm_utils

TOOL_CAPABLE_MODELS = frozenset(
    {
        "openrouter/openai/gpt-oss-20b:free",
        "openrouter/openai/gpt-oss-120b:free",
        "openrouter/openrouter/free",
        "nvidia_nim/z-ai/glm-5.1",
    }
)

_TOOL_PREFIXES = (
    "openrouter/",
    "nvidia_nim/",
)


def _openrouter_model(model: str) -> bool:
    if model in TOOL_CAPABLE_MODELS:
        return True
    return any(model.startswith(prefix) for prefix in _TOOL_PREFIXES)


def _message_text(message) -> str:
    content = getattr(message, "content", None)
    if isinstance(content, str) and content.strip():
        return content
    reasoning = getattr(message, "reasoning_content", None)
    if reasoning:
        return reasoning
    fields = getattr(message, "provider_specific_fields", None) or {}
    if isinstance(fields, dict):
        reasoning = fields.get("reasoning")
        if reasoning:
            return str(reasoning)
    return content or ""


def _normalize_tool_calls(tool_calls) -> list[dict] | dict | None:
    if not tool_calls:
        return None
    normalized: list[dict] = []
    for tool_call in tool_calls:
        if isinstance(tool_call, dict):
            if "function" in tool_call:
                normalized.append(tool_call)
            continue
        fn = tool_call.function
        normalized.append(
            {
                "id": getattr(tool_call, "id", "tool-call"),
                "type": "function",
                "function": {
                    "name": fn.name,
                    "arguments": fn.arguments,
                },
            }
        )
    if not normalized:
        return None
    return normalized


_orig_supports_function_calling = litellm_utils.supports_function_calling
_orig_supports_parallel_function_calling = (
    litellm_utils.supports_parallel_function_calling
)


def supports_function_calling(model: str, custom_llm_provider=None) -> bool:
    if _openrouter_model(model):
        return True
    return _orig_supports_function_calling(
        model, custom_llm_provider=custom_llm_provider
    )


def supports_parallel_function_calling(model: str, custom_llm_provider=None) -> bool:
    if _openrouter_model(model):
        return True
    return _orig_supports_parallel_function_calling(
        model, custom_llm_provider=custom_llm_provider
    )


def _get_version(mod) -> str:
    return getattr(mod, "__version__", "") or getattr(mod, "version", "")


def apply_swarms_patches() -> None:
    litellm_utils.supports_function_calling = supports_function_calling
    litellm_utils.supports_parallel_function_calling = (
        supports_parallel_function_calling
    )

    try:
        from swarms.utils.litellm_wrapper import LiteLLM

        if not hasattr(LiteLLM, "output_for_tools"):
            raise ImportError("LiteLLM.output_for_tools missing — swarms version mismatch")
        _orig_output_for_tools = LiteLLM.output_for_tools
        _orig_run = LiteLLM.run

        def output_for_tools(self, response):  # type: ignore[no-untyped-def]
            message = response.choices[0].message
            tool_calls = _normalize_tool_calls(
                getattr(message, "tool_calls", None)
            )
            if tool_calls is not None:
                return tool_calls
            text = _message_text(message)
            return text if text else None

        def run(self, task, audio=None, img=None, *args, **kwargs):  # type: ignore[no-untyped-def]
            result = _orig_run(self, task, audio, img, *args, **kwargs)
            if result is not None:
                return result
            return ""

        LiteLLM.output_for_tools = output_for_tools  # type: ignore[method-assign]
        LiteLLM.run = run  # type: ignore[method-assign]
    except ImportError:
        pass

    try:
        import swarms.structs.agent as agent_mod

        agent_mod.supports_function_calling = supports_function_calling
        agent_mod.supports_parallel_function_calling = (
            supports_parallel_function_calling
        )

        _orig_reliability = agent_mod.Agent.reliability_check

        def quiet_reliability(self):  # type: ignore[no-untyped-def]
            if self.system_prompt is None:
                return
            if self.agent_name is None:
                return
            if self.max_loops is None or self.max_loops == 0:
                raise agent_mod.AgentInitializationError(
                    "Max loops is not provided or is set to 0. Please set max loops to 1 or more."
                )
            if self.context_length is None or self.context_length == 0:
                raise agent_mod.AgentInitializationError(
                    "Context length is not provided. Please set a valid context length."
                )
            if self.max_tokens is None or self.max_tokens <= 0:
                self.max_tokens = 8192

        agent_mod.Agent.reliability_check = quiet_reliability  # type: ignore[method-assign]

        _orig_parse = agent_mod.Agent.parse_llm_output

        def parse_llm_output(self, response):  # type: ignore[no-untyped-def]
            if response is None:
                return ""
            if isinstance(response, list):
                return response
            if isinstance(response, dict) and "function" in response:
                return response
            parsed = _orig_parse(self, response)
            return parsed if parsed is not None else ""

        agent_mod.Agent.parse_llm_output = parse_llm_output  # type: ignore[method-assign]

        _orig_execute_tools = agent_mod.Agent.execute_tools

        def execute_tools(self, response, loop_count: int = 0, **kwargs):  # type: ignore[no-untyped-def]
            try:
                return _orig_execute_tools(self, response, loop_count)
            except Exception as exc:
                err = str(exc)
                if "not found in tools" not in err:
                    raise
                from autohedge.tools.blofin_registry import (
                    BLOFIN_TOOL_REGISTRY,
                    call_blofin_tool,
                )

                calls: list[dict] = []
                if isinstance(response, dict) and "function" in response:
                    calls = [response]
                elif isinstance(response, list):
                    calls = [tc for tc in response if isinstance(tc, dict)]

                agent_tools = {
                    getattr(t, "__name__", str(t)): t for t in (self.tools or [])
                }
                results: list[dict] = []
                for tool_call in calls:
                    name = tool_call.get("function", {}).get("name", "")
                    if name in agent_tools or name not in BLOFIN_TOOL_REGISTRY:
                        raise
                    try:
                        arguments = json.loads(
                            tool_call.get("function", {}).get("arguments", "{}")
                        )
                    except (json.JSONDecodeError, TypeError):
                        arguments = {}
                    output = call_blofin_tool(name, arguments)
                    results.append(
                        {
                            "tool_call_id": tool_call.get("id", name),
                            "role": "tool",
                            "name": name,
                            "content": output,
                        }
                    )
                if results:
                    return results
                raise

        agent_mod.Agent.execute_tools = execute_tools  # type: ignore[method-assign]

        _orig_tool_execution_retry = agent_mod.Agent.tool_execution_retry

        def tool_execution_retry(self, response, loop_count):  # type: ignore[no-untyped-def]
            if response is None:
                return _orig_tool_execution_retry(self, response, loop_count)

            calls: list[dict] = []
            if isinstance(response, dict) and "function" in response:
                calls = [response]
            elif isinstance(response, list):
                calls = [tc for tc in response if isinstance(tc, dict)]

            handoffs: list[dict] = []
            regular: list[dict] = []
            for tool_call in calls:
                name = tool_call.get("function", {}).get("name")
                if name == "handoff_task":
                    handoffs.append(tool_call)
                else:
                    regular.append(tool_call)

            for tool_call in handoffs:
                try:
                    arguments = json.loads(
                        tool_call.get("function", {}).get("arguments", "{}")
                    )
                except (json.JSONDecodeError, TypeError):
                    arguments = {}
                self._handoff_task_tool(handoffs=arguments.get("handoffs", []))

            if not regular:
                return None
            if len(regular) == 1:
                return _orig_tool_execution_retry(self, regular[0], loop_count)
            return _orig_tool_execution_retry(self, regular, loop_count)

        agent_mod.Agent.tool_execution_retry = tool_execution_retry  # type: ignore[method-assign]

        import swarms.tools.handoffs_tool as handoffs_mod

        handoffs_mod.handoff_task = ordered_handoff_task
        # Agent imports handoff_task by name; patch that binding too.
        agent_mod.handoff_task = ordered_handoff_task
    except ImportError:
        pass


apply_swarms_patches()
