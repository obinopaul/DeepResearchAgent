from src.config.agents import AGENT_LLM_MAP
from src.prompts.template import apply_prompt_template
from src.llms.llm import get_llm_by_type, get_llm_token_limit_by_type


def get_default_model():
    # Use the dedicated deepagent model type for orchestration
    return get_llm_by_type(AGENT_LLM_MAP["deepagent_openai"])
