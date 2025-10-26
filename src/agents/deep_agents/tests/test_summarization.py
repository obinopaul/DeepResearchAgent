import pytest

from langchain_core.language_models.chat_models import BaseChatModel

from src.agents.deep_agents.middleware.summarization import (
    compute_summary_budget,
    resolve_token_limit,
)
from src.llms.llm import get_llm_token_limit_by_type


class DummyChatModel(BaseChatModel):
    """Minimal chat model stub exposing anthropic-style attributes."""

    model_name: str = "claude-sonnet-4-20250514"
    max_tokens: int = 20000
    model_kwargs: dict[str, int] = {"max_tokens": 20000}

    class Config:
        extra = "allow"

    def __init__(self, model_name: str = "claude-sonnet-4-20250514", max_tokens: int = 20000):
        super().__init__(
            model_name=model_name,
            max_tokens=max_tokens,
            model_kwargs={"max_tokens": max_tokens},
        )

    @property
    def _llm_type(self) -> str:
        return "dummy"

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):  # noqa: D401, ANN001
        raise NotImplementedError("Dummy model does not implement generation")


class TestResolveTokenLimit:
    def test_resolve_token_limit_ignores_completion_cap(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("DEEPAGENT_MODEL__token_limit", raising=False)
        monkeypatch.delenv("DEEP_AGENT_MODEL_TOKEN_LIMIT", raising=False)
        dummy = DummyChatModel()
        token_limit = resolve_token_limit(dummy)
        assert token_limit == get_llm_token_limit_by_type("deepagent")

    def test_resolve_token_limit_respects_env_override(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("DEEPAGENT_MODEL__token_limit", "180000")
        dummy = DummyChatModel()
        token_limit = resolve_token_limit(dummy)
        assert token_limit == 180000


class TestComputeSummaryBudget:
    def test_large_context_window_keeps_history(self) -> None:
        token_limit = 200_000
        budget = compute_summary_budget(token_limit)
        assert budget == 180_000

    def test_small_context_window_still_reserves_half(self) -> None:
        token_limit = 8_192
        budget = compute_summary_budget(token_limit)
        assert budget == 4_096

    def test_requested_budget_is_clamped_within_safe_bounds(self) -> None:
        token_limit = 200_000
        assert compute_summary_budget(token_limit, requested=160_000) == 160_000
        assert compute_summary_budget(token_limit, requested=190_000) == 180_000
