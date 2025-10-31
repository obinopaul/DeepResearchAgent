"""langgraph.prebuilt exposes a higher-level API for creating and executing agents and tools."""

def __getattr__(name):
    if name == "create_agent":
        from src.agents.agents.react_agent import create_agent
        return create_agent
    elif name == "AgentState":
        from src.agents.agents.middleware.types import AgentState
        return AgentState
    else:
        raise AttributeError(f"module {__name__} has no attribute {name}")

__all__ = [
    "AgentState",
    "create_agent",
]
