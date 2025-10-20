from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.agents.deep_agents.graph import create_deep_agent, async_create_deep_agent
    from src.agents.deep_agents.middleware import (
        PlanningMiddleware,
        FilesystemMiddleware,
        InsightLoggingMiddleware,
        SubAgentMiddleware,
    )
    from src.agents.deep_agents.state import DeepAgentState
    from src.agents.deep_agents.types import SubAgent, CustomSubAgent
    from src.agents.deep_agents.model import get_default_model


def __getattr__(name):
    if name == "create_deep_agent":
        from src.agents.deep_agents.graph import create_deep_agent
        return create_deep_agent
    elif name == "async_create_deep_agent":
        from src.agents.deep_agents.graph import async_create_deep_agent
        return async_create_deep_agent
    elif name == "PlanningMiddleware":
        from src.agents.deep_agents.middleware import PlanningMiddleware
        return PlanningMiddleware
    elif name == "FilesystemMiddleware":
        from src.agents.deep_agents.middleware import FilesystemMiddleware
        return FilesystemMiddleware
    elif name == "InsightLoggingMiddleware":
        from src.agents.deep_agents.middleware import InsightLoggingMiddleware
        return InsightLoggingMiddleware
    elif name == "SubAgentMiddleware":
        from src.agents.deep_agents.middleware import SubAgentMiddleware
        return SubAgentMiddleware
    elif name == "DeepAgentState":
        from src.agents.deep_agents.state import DeepAgentState
        return DeepAgentState
    elif name == "SubAgent":
        from src.agents.deep_agents.types import SubAgent
        return SubAgent
    elif name == "CustomSubAgent":
        from src.agents.deep_agents.types import CustomSubAgent
        return CustomSubAgent
    elif name == "get_default_model":
        from src.agents.deep_agents.model import get_default_model
        return get_default_model
    else:
        raise AttributeError(f"module {__name__} has no attribute {name}")


__all__ = [
    "create_deep_agent",
    "async_create_deep_agent",
    "PlanningMiddleware",
    "FilesystemMiddleware",
    "InsightLoggingMiddleware",
    "SubAgentMiddleware",
    "DeepAgentState",
    "SubAgent",
    "CustomSubAgent",
    "get_default_model",
]
