# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import os
from typing import Literal, get_args

LLMType = Literal[
    "basic",
    "synthesizer",
    "reasoning",
    "vision",
    "code",
    "deepagent",
    "deepagent_openai",
    "deepagent_deepseek",
]

_DEEP_AGENT_ENV_ALIAS_MAP = {
    "anthropic": "deepagent",
    "claude": "deepagent",
    "claude-3": "deepagent",
    "claude-3.5": "deepagent",
    "default": "deepagent",
    "deepseek": "deepagent_openai",
    "openai": "deepagent_openai",
    "gpt": "deepagent_openai",
    "gpt-4": "deepagent_openai",
    "gpt-4o": "deepagent_openai",
    "deepseek": "deepagent_deepseek",
    "deepseek-chat": "deepagent_deepseek",
}

def _resolve_deepagent_llm_type() -> LLMType:
    """Resolve which LLM variant the deep agent orchestration should use."""
    # Preferred env var allows specifying exact llm type name.
    explicit_type = os.getenv("DEEP_AGENT_LLM_TYPE")
    if explicit_type:
        normalized = explicit_type.strip().lower()
        mapped = _DEEP_AGENT_ENV_ALIAS_MAP.get(normalized, normalized)
        if mapped not in get_args(LLMType):
            raise ValueError(
                f"Unsupported DEEP_AGENT_LLM_TYPE '{explicit_type}'. "
                f"Supported values: {', '.join(sorted(get_args(LLMType)))} "
                f"or provider aliases: {', '.join(sorted(_DEEP_AGENT_ENV_ALIAS_MAP))}"
            )
        return mapped  # type: ignore[return-value]

    provider = os.getenv("DEEP_AGENT_PROVIDER")
    if provider:
        normalized = provider.strip().lower()
        mapped = _DEEP_AGENT_ENV_ALIAS_MAP.get(normalized)
        if mapped and mapped in get_args(LLMType):
            return mapped  # type: ignore[return-value]
        raise ValueError(
            f"Unsupported DEEP_AGENT_PROVIDER '{provider}'. "
            f"Supported provider aliases: {', '.join(sorted(_DEEP_AGENT_ENV_ALIAS_MAP))}"
        )

    # Default behaviour remains Anthropic-backed deep agent.
    return "deepagent"

DEEPAGENT_LLM_TYPE: LLMType = _resolve_deepagent_llm_type()

# Define agent-LLM mapping
AGENT_LLM_MAP: dict[str, LLMType] = {
    "coordinator": "basic",
    "planner": "basic",
    "researcher": "basic",
    "coder": "basic",
    "reporter": "basic",
    "podcast_script_writer": "basic",
    "ppt_composer": "basic",
    "prose_writer": "basic",
    "prompt_enhancer": "basic",
    "synthesizer": "synthesizer",
    # Dedicated model selection for deep agent orchestration
    "deepagent": DEEPAGENT_LLM_TYPE,
    "deepagent_openai": DEEPAGENT_LLM_TYPE,
    "deepagent_deepseek": DEEPAGENT_LLM_TYPE,
}
