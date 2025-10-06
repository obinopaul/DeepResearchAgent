# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

# from langgraph.prebuilt import create_react_agent
from src.agents.agents import create_agent as create_react_agent
from src.config.agents import AGENT_LLM_MAP
from src.llms.llm import get_llm_by_type
from src.prompts import apply_prompt_template
from src.agents.deep_agents import DeepAgentState, create_deep_agent, async_create_deep_agent

# Create agents using configured LLM types
def create_agent(
    agent_name: str,
    agent_type: str,
    tools: list,
    prompt_template: str,
    pre_model_hook: callable = None,
):
    """Factory function to create agents with consistent configuration."""
    return create_react_agent(
        name=agent_name,
        model=get_llm_by_type(AGENT_LLM_MAP[agent_type]),
        tools=tools,
        prompt=lambda state: apply_prompt_template(prompt_template, state),
        pre_model_hook=pre_model_hook,
    )





def deep_agent(
    agent_name: str,
    agent_type: str,
    tools: list,
    prompt_template: str,
    sub_research_prompt: str,
    sub_critique_prompt: str,
    pre_model_hook: callable = None,
):
    
    research_sub_agent = {
        "name": "research-agent",
        "description": "Used to research more in depth questions. Only give this researcher one topic at a time. Do not pass multiple sub questions to this researcher. Instead, you should break down a large topic into the necessary components, and then call multiple research agents in parallel, one for each sub question.",
        "prompt": sub_research_prompt,
        "tools": tools,
    }

    critique_sub_agent = {
        "name": "critique-agent",
        "description": "Used to critique the final report. Give this agent some information about how you want it to critique the report.",
        "prompt": sub_critique_prompt,
    }

    """Factory function to create agents with consistent configuration."""
    return create_deep_agent(
        # name=agent_name,
        model=get_llm_by_type(AGENT_LLM_MAP[agent_type]),
        tools=tools,
        subagents=[critique_sub_agent, research_sub_agent],
        # instructions =lambda state: apply_prompt_template(prompt_template, state),
        instructions=prompt_template,
        # pre_model_hook=pre_model_hook,
    ).with_config({"recursion_limit": 1000})
    