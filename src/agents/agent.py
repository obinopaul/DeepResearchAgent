# Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
# SPDX-License-Identifier: MIT

# from langgraph.prebuilt import create_react_agent
from langchain.agents import create_agent as create_react_agent
from src.config.agents import AGENT_LLM_MAP
from src.llms.llm import get_llm_by_type
from src.prompts import apply_prompt_template
from src.agents.deep_agents import ResearchTimerMiddleware, create_deep_agent

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
    sub_query_optimizer_prompt: str,
    sub_insight_extractor_prompt: str,
    sub_followup_prompt: str,
    sub_evidence_auditor_prompt: str,
    pre_model_hook: callable = None,
    research_timer_seconds: float | int | None = None,
):
    
    research_sub_agent = {
        "name": "research-agent",
        "description": "Used to research more in depth questions. Only give this researcher one topic at a time. Do not pass multiple sub questions to this researcher. Instead, you should break down a large topic into the necessary components, and then call multiple research agents in parallel, one for each sub question.",
        "system_prompt": sub_research_prompt,
        "tools": tools,
    }

    critique_sub_agent = {
        "name": "critique-agent",
        "description": "Used to critique the final report. Give this agent some information about how you want it to critique the report.",
        "system_prompt": sub_critique_prompt,
    }

    query_optimizer_sub_agent = {
        "name": "query-strategist",
        "description": (
            "Refines broad or ambiguous requests into precise, high-signal research directives "
            "and highlights assumptions that must be validated."
        ),
        "system_prompt": sub_query_optimizer_prompt,
        "tools": [],
    }

    insight_extractor_sub_agent = {
        "name": "insight-synthesizer",
        "description": (
            "Transforms raw crawled material into relevance-scored insights with evidence, implications and gaps."
        ),
        "system_prompt": sub_insight_extractor_prompt,
        "tools": tools,
    }

    followup_architect_sub_agent = {
        "name": "exploration-architect",
        "description": (
            "Identifies high-leverage follow-up investigations, counterfactual checks, and monitoring hooks."
        ),
        "system_prompt": sub_followup_prompt,
        "tools": [],
    }

    evidence_auditor_sub_agent = {
        "name": "evidence-auditor",
        "description": (
            "Audits draft findings for evidentiary strength, missing citations, quantitative accuracy, and risk coverage."
        ),
        "system_prompt": sub_evidence_auditor_prompt,
        "tools": tools,
    }

    all_subagents = [
        critique_sub_agent,
        research_sub_agent,
        query_optimizer_sub_agent,
        insight_extractor_sub_agent,
        followup_architect_sub_agent,
        evidence_auditor_sub_agent,
    ]

    extra_middleware = []
    if research_timer_seconds is not None:
        try:
            seconds = float(research_timer_seconds)
        except (TypeError, ValueError):
            seconds = None
        if seconds and seconds > 0:
            extra_middleware.append(ResearchTimerMiddleware(total_seconds=seconds))

    """Factory function to create agents with consistent configuration."""
    # Always use the dedicated deepagent LLM type for orchestration, independent of the caller's agent_type
    return create_deep_agent(
        # name=agent_name,
        model=get_llm_by_type(AGENT_LLM_MAP["deepagent"]),
        tools=tools,
        subagents=all_subagents,
        # instructions =lambda state: apply_prompt_template(prompt_template, state),
        system_prompt=prompt_template,
        # pre_model_hook=pre_model_hook,
        middleware=extra_middleware or None,
    ).with_config({"recursion_limit": 1000})
    
