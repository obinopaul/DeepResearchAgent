# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

# def __getattr__(name):
#     if name == "create_agent":
#         from .agents import create_agent
#         return create_agent
#     if name == "deep_agent":
#         from .agents import deep_agent
#         return deep_agent
#     raise AttributeError(f"module {__name__} has no attribute {name}")

# __all__ = ["create_agent", "deep_agent"]


from .agent import create_agent, deep_agent

__all__ = ["create_agent", "deep_agent"]