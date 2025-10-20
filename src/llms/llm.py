# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

import logging
import os
from pathlib import Path
from typing import Any, Dict, get_args

import httpx
from langchain_core.language_models import BaseChatModel

try:
    from langchain_anthropic import ChatAnthropic
except ImportError:  # pragma: no cover - optional dependency
    ChatAnthropic = None  # type: ignore[assignment]

try:
    from langchain_deepseek import ChatDeepSeek
except ImportError:  # pragma: no cover - optional dependency
    ChatDeepSeek = None  # type: ignore[assignment]

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except ImportError:  # pragma: no cover - optional dependency
    ChatGoogleGenerativeAI = None  # type: ignore[assignment]

try:
    from langchain_openai import AzureChatOpenAI, ChatOpenAI
except ImportError:  # pragma: no cover - optional dependency
    AzureChatOpenAI = None  # type: ignore[assignment]
    ChatOpenAI = None  # type: ignore[assignment]

from src.config import load_yaml_config
from src.config.agents import LLMType
from src.llms.providers.dashscope import ChatDashscope

DEFAULT_TOKEN_LIMITS: dict[str, int] = {
    "basic": 8192,
    "reasoning": 128000,
    "vision": 8192,
    "code": 8192,
    "deepagent": 200000,
    "deepagent_openai": 128000,
    "deepagent_deepseek": 131072,
}

logger = logging.getLogger(__name__)

# Cache for LLM instances
_llm_cache: dict[LLMType, BaseChatModel] = {}


def _get_config_file_path() -> str:
    """Get the path to the configuration file."""
    return str((Path(__file__).parent.parent.parent / "conf.yaml").resolve())


def _get_llm_type_config_keys() -> dict[str, str]:
    """Get mapping of LLM types to their configuration keys."""
    return {
        "reasoning": "REASONING_MODEL",
        "basic": "BASIC_MODEL",
        "vision": "VISION_MODEL",
        "code": "CODE_MODEL",
        "deepagent": "DEEPAGENT_MODEL",
        "deepagent_openai": "DEEPAGENT_MODEL",
        "deepagent_deepseek": "DEEPAGENT_MODEL",
    }


def _get_env_llm_conf(llm_type: str) -> Dict[str, Any]:
    """
    Get LLM configuration from environment variables.
    Environment variables should follow the format: {LLM_TYPE}__{KEY}
    e.g., BASIC_MODEL__api_key, BASIC_MODEL__base_url
    """
    prefix = f"{llm_type.upper()}_MODEL__"
    conf = {}
    for key, value in os.environ.items():
        if key.startswith(prefix):
            conf_key = key[len(prefix) :].lower()
            conf[conf_key] = value
    return conf


def _create_llm_use_conf(llm_type: LLMType, conf: Dict[str, Any]) -> BaseChatModel:
    """Create LLM instance using configuration."""
    llm_type_config_keys = _get_llm_type_config_keys()
    config_key = llm_type_config_keys.get(llm_type)

    if not config_key:
        raise ValueError(f"Unknown LLM type: {llm_type}")

    llm_conf = conf.get(config_key, {})
    if not isinstance(llm_conf, dict):
        raise ValueError(f"Invalid LLM configuration for {llm_type}: {llm_conf}")

    # Get configuration from environment variables
    env_conf = _get_env_llm_conf(llm_type)

    # Merge configurations, with environment variables taking precedence
    merged_conf = {**llm_conf, **env_conf}

    # Remove unnecessary parameters when initializing the client
    if "token_limit" in merged_conf:
        merged_conf.pop("token_limit")

    # Deepagent: prefer Anthropic for orchestration. Allow sane defaults even if no config provided.
    if llm_type == "deepagent":
        if ChatAnthropic is None:
            raise ImportError(
                "langchain-anthropic is required for deepagent orchestration. "
                "Install it with `pip install langchain-anthropic`."
            )
        # Defaults with env overrides
        model_name = (
            merged_conf.get("model")
            or merged_conf.get("model_name")
            or "claude-sonnet-4-20250514"
        )
        try:
            requested_max_tokens = int(merged_conf.get("max_tokens", 20000))
        except Exception:
            requested_max_tokens = 20000

        # Claude Sonnet 3.5 has a 200k context window; leave a safety margin so we don't exceed it.
        safe_max_tokens = min(requested_max_tokens, 180000)

        if safe_max_tokens != requested_max_tokens:
            logger.warning(
                "Requested deep agent max_tokens=%s exceeds safety margin for Claude context window; "
                "clamping to %s tokens.",
                requested_max_tokens,
                safe_max_tokens,
            )

        kwargs: Dict[str, Any] = {"model_name": model_name, "max_tokens": safe_max_tokens}
        # Pick up API key from namespaced config or global ANTHROPIC_API_KEY
        api_key = (
            merged_conf.get("api_key")
            or merged_conf.get("anthropic_api_key")
            or os.getenv("ANTHROPIC_API_KEY")
        )
        if api_key:
            kwargs["anthropic_api_key"] = api_key
        return ChatAnthropic(**kwargs)


    # Deepagent: prefer openai for orchestration. Allow sane defaults even if no config provided.
    if llm_type == "deepagent_openai":
        # Defaults with env overrides
        model_name = (
            merged_conf.get("model")
            or merged_conf.get("model_name")
            or "gpt-4.1-nano"
        )
        try:
            max_tokens = int(merged_conf.get("max_tokens", 32000))
        except Exception:
            max_tokens = 32000
        kwargs: Dict[str, Any] = {"model_name": model_name, "max_tokens": max_tokens}
        # Pick up API key from namespaced config or global ANTHROPIC_API_KEY
        api_key = (
            merged_conf.get("api_key")
            or merged_conf.get("openai_api_key")
            or os.getenv("OPENAI_API_KEY")
        )
        if api_key:
            kwargs["openai_api_key"] = api_key
        if ChatOpenAI is None:
            raise ImportError(
                "langchain-openai is required for deepagent_openai. Install it with `pip install langchain-openai`."
            )
        return ChatOpenAI(**kwargs)

    # Deepagent: DeepSeek compatible interface.
    if llm_type == "deepagent_deepseek":
        model_name = (
            merged_conf.get("model")
            or merged_conf.get("model_name")
            or "deepseek-chat"
        )
        temperature = merged_conf.get("temperature", 0)
        try:
            temperature = float(temperature)
        except Exception:
            temperature = 0.0

        max_tokens = merged_conf.get("max_tokens")
        if max_tokens is not None:
            try:
                max_tokens = int(max_tokens)
            except Exception:
                max_tokens = None

        kwargs: Dict[str, Any] = {
            "model": model_name,
            "temperature": temperature,
            "timeout": merged_conf.get("timeout"),
            "max_retries": merged_conf.get("max_retries", 2),
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens

        api_key = (
            merged_conf.get("api_key")
            or merged_conf.get("deepseek_api_key")
            or os.getenv("DEEPSEEK_API_KEY")
        )
        if api_key:
            kwargs["api_key"] = api_key

        base_url = merged_conf.get("base_url")
        if base_url:
            kwargs["base_url"] = base_url

        if ChatDeepSeek is None:
            raise ImportError(
                "langchain-deepseek is required for deepagent_deepseek. Install it with `pip install langchain-deepseek`."
            )
        return ChatDeepSeek(**kwargs)
    
    if not merged_conf:
        raise ValueError(f"No configuration found for LLM type: {llm_type}")

    # Add max_retries to handle rate limit errors
    if "max_retries" not in merged_conf:
        merged_conf["max_retries"] = 3

    # Handle SSL verification settings
    verify_ssl = merged_conf.pop("verify_ssl", True)

    # Create custom HTTP client if SSL verification is disabled
    if not verify_ssl:
        http_client = httpx.Client(verify=False)
        http_async_client = httpx.AsyncClient(verify=False)
        merged_conf["http_client"] = http_client
        merged_conf["http_async_client"] = http_async_client

    # Check if it's Google AI Studio platform based on configuration
    platform = merged_conf.get("platform", "").lower()
    is_google_aistudio = platform == "google_aistudio" or platform == "google-aistudio"

    if is_google_aistudio:
        # Handle Google AI Studio specific configuration
        gemini_conf = merged_conf.copy()

        # Map common keys to Google AI Studio specific keys
        if "api_key" in gemini_conf:
            gemini_conf["google_api_key"] = gemini_conf.pop("api_key")

        # Remove base_url and platform since Google AI Studio doesn't use them
        gemini_conf.pop("base_url", None)
        gemini_conf.pop("platform", None)

        # Remove unsupported parameters for Google AI Studio
        gemini_conf.pop("http_client", None)
        gemini_conf.pop("http_async_client", None)

        if ChatGoogleGenerativeAI is None:
            raise ImportError(
                "langchain-google-genai is required for Google AI Studio models. Install it with `pip install langchain-google-genai`."
            )
        return ChatGoogleGenerativeAI(**gemini_conf)

    if "azure_endpoint" in merged_conf or os.getenv("AZURE_OPENAI_ENDPOINT"):
        if AzureChatOpenAI is None:
            raise ImportError(
                "langchain-openai is required for Azure OpenAI. Install it with `pip install langchain-openai`."
            )
        return AzureChatOpenAI(**merged_conf)

    # Check if base_url is dashscope endpoint
    if "base_url" in merged_conf and "dashscope." in merged_conf["base_url"]:
        if llm_type == "reasoning":
            merged_conf["extra_body"] = {"enable_thinking": True}
        else:
            merged_conf["extra_body"] = {"enable_thinking": False}
        return ChatDashscope(**merged_conf)

    if llm_type == "reasoning":
        merged_conf["api_base"] = merged_conf.pop("base_url", None)
        if ChatDeepSeek is None:
            raise ImportError(
                "langchain-deepseek is required for reasoning models. Install it with `pip install langchain-deepseek`."
            )
        return ChatDeepSeek(**merged_conf)

    if ChatOpenAI is None:
        raise ImportError(
            "langchain-openai is required for OpenAI chat models. Install it with `pip install langchain-openai`."
        )
    return ChatOpenAI(**merged_conf)


def get_llm_by_type(llm_type: LLMType) -> BaseChatModel:
    """
    Get LLM instance by type. Returns cached instance if available.
    """
    if llm_type in _llm_cache:
        return _llm_cache[llm_type]

    conf = load_yaml_config(_get_config_file_path())
    llm = _create_llm_use_conf(llm_type, conf)
    _llm_cache[llm_type] = llm
    return llm


def get_configured_llm_models() -> dict[str, list[str]]:
    """
    Get all configured LLM models grouped by type.

    Returns:
        Dictionary mapping LLM type to list of configured model names.
    """
    try:
        conf = load_yaml_config(_get_config_file_path())
        llm_type_config_keys = _get_llm_type_config_keys()

        configured_models: dict[str, list[str]] = {}

        for llm_type in get_args(LLMType):
            # Get configuration from YAML file
            config_key = llm_type_config_keys.get(llm_type, "")
            yaml_conf = conf.get(config_key, {}) if config_key else {}

            # Get configuration from environment variables
            env_conf = _get_env_llm_conf(llm_type)

            # Merge configurations, with environment variables taking precedence
            merged_conf = {**yaml_conf, **env_conf}

            # Check if model is configured (Anthropic may use model_name)
            model_name = merged_conf.get("model") or merged_conf.get("model_name")
            if model_name:
                configured_models.setdefault(llm_type, []).append(model_name)

        return configured_models

    except Exception as e:
        # Log error and return empty dict to avoid breaking the application
        print(f"Warning: Failed to load LLM configuration: {e}")
        return {}


def get_llm_token_limit_by_type(llm_type: str) -> int:
    """
    Get the maximum token limit for a given LLM type.

    Args:
        llm_type (str): The type of LLM.

    Returns:
        int: The maximum token limit for the specified LLM type.
    """

    llm_type_config_keys = _get_llm_type_config_keys()
    config_key = llm_type_config_keys.get(llm_type)

    env_conf = _get_env_llm_conf(llm_type)
    token_limit = env_conf.get("token_limit")

    if token_limit is None and config_key:
        conf = load_yaml_config(_get_config_file_path())
        token_limit = conf.get(config_key, {}).get("token_limit")

    if token_limit is not None:
        try:
            return int(token_limit)
        except (TypeError, ValueError):
            logger.warning(
                "Invalid token_limit '%s' for llm_type '%s'; falling back to defaults.",
                token_limit,
                llm_type,
            )

    default_limit = DEFAULT_TOKEN_LIMITS.get(llm_type)
    if default_limit is None:
        logger.warning(
            "No token limit configured for llm_type '%s'; defaulting to 8192 tokens.", llm_type
        )
        return 8192
    return default_limit


# In the future, we will use reasoning_llm and vl_llm for different purposes
# reasoning_llm = get_llm_by_type("reasoning")
# vl_llm = get_llm_by_type("vision")
