# from langchain_anthropic import ChatAnthropic
from src.config.agents import AGENT_LLM_MAP
from src.prompts.template import apply_prompt_template
from src.llms.llm import get_llm_by_type, get_llm_token_limit_by_type


# def get_default_model():
#     return ChatAnthropic(model_name="claude-sonnet-4-20250514", max_tokens=64000)


def get_default_model():
    return get_llm_by_type(AGENT_LLM_MAP["planner"])
