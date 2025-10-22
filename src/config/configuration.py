# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
import os
from dataclasses import dataclass, field, fields
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig

from src.config.loader import get_bool_env, get_int_env, get_str_env
from src.config.report_style import ReportStyle
from src.rag.retriever import Resource

logger = logging.getLogger(__name__)


def get_recursion_limit(default: int = 25) -> int:
    """Get the recursion limit from environment variable or use default.

    Args:
        default: Default recursion limit if environment variable is not set or invalid

    Returns:
        int: The recursion limit to use
    """
    env_value_str = get_str_env("AGENT_RECURSION_LIMIT", str(default))
    parsed_limit = get_int_env("AGENT_RECURSION_LIMIT", default)

    if parsed_limit > 0:
        logger.info(f"Recursion limit set to: {parsed_limit}")
        return parsed_limit
    else:
        logger.warning(
            f"AGENT_RECURSION_LIMIT value '{env_value_str}' (parsed as {parsed_limit}) is not positive. "
            f"Using default value {default}."
        )
        return default


@dataclass(kw_only=True)
class Configuration:
    """The configurable fields."""

    resources: list[Resource] = field(
        default_factory=list
    )  # Resources to be used for the research
    max_plan_iterations: int = 1  # Maximum number of plan iterations
    max_step_num: int = 3  # Maximum number of steps in a plan
    max_search_results: int = 3  # Maximum number of search results
    mcp_settings: dict = None  # MCP settings, including dynamic loaded tools
    report_style: str = ReportStyle.ACADEMIC.value  # Report style
    enable_deep_thinking: bool = False  # Whether to enable deep thinking
    research_timer_seconds: Optional[int] = None  # Research timer budget

    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> "Configuration":
        """Create a Configuration instance from a RunnableConfig."""
        configurable = {}
        if config and isinstance(config, dict):
            raw_configurable = config.get("configurable")
            if isinstance(raw_configurable, dict):
                configurable = raw_configurable

        field_names = {f.name for f in fields(cls) if f.init}
        top_level_values: dict[str, Any] = {}
        if config and isinstance(config, dict):
            top_level_values = {
                key: value
                for key, value in config.items()
                if key in field_names
            }

        values: dict[str, Any] = {}
        for field_def in fields(cls):
            if not field_def.init:
                continue
            key = field_def.name
            env_key = key.upper()
            env_value = os.environ.get(env_key)
            if env_value not in (None, ""):
                values[key] = env_value
                continue

            candidate = configurable.get(key)
            if candidate in (None, "", False, 0):
                candidate = top_level_values.get(key)
            if candidate not in (None, "", False, 0):
                values[key] = candidate

        return cls(**values)
