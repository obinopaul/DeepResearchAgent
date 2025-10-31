"""Adaptive summarization middleware for DeepAgent."""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import (
    AIMessage,
    AnyMessage,
    HumanMessage,
    RemoveMessage,
    ToolMessage,
)
from langchain_core.messages.utils import count_tokens_approximately

from langchain.agents.middleware.summarization import SummarizationMiddleware
from langchain.agents.middleware.types import AgentState
from langgraph.runtime import Runtime
from src.config.agents import AGENT_LLM_MAP, DEEPAGENT_LLM_TYPE
from src.llms.llm import get_llm_token_limit_by_type

logger = logging.getLogger(__name__)

_ENV_TOKEN_LIMIT_KEYS: tuple[str, ...] = (
    "DEEP_AGENT_MODEL_TOKEN_LIMIT",
    "DEEPAGENT_MODEL_TOKEN_LIMIT",
    "DEEP_AGENT_CONTEXT_WINDOW",
    "DEEPAGENT_MODEL__TOKEN_LIMIT",
    "DEEPAGENT_MODEL__token_limit",
)
_ENV_SUMMARY_BUDGET_KEYS: tuple[str, ...] = (
    "DEEP_AGENT_SUMMARY_BUDGET",
    "DEEP_AGENT_MAX_TOKENS",
    "DEEP_AGENT_MAXIMUM_TOKENS",
    "DEEPAGENT_MODEL_MAX_TOKENS",
    "DEEPAGENT_MODEL__MAX_TOKENS",
    "DEEPAGENT_MODEL__max_tokens",
)


def _read_int_from_env(keys: Sequence[str]) -> int | None:
    """Attempt to read the first valid integer from a list of env vars."""
    for key in keys:
        raw_value = os.getenv(key)
        if raw_value is None:
            continue
        value = raw_value.strip()
        if not value:
            continue
        try:
            parsed = int(value)
        except ValueError:
            logger.warning(
                "Ignoring invalid integer value for %s=%r when resolving DeepAgent token budgets.",
                key,
                raw_value,
            )
            continue
        if parsed > 0:
            return parsed
    return None


def _infer_llm_type_from_name(model_name: str) -> str | None:
    """Infer the configured LLM type from a raw model identifier."""
    if not model_name:
        return None

    if model_name in AGENT_LLM_MAP:
        return AGENT_LLM_MAP[model_name]

    if "deepseek" in model_name:
        return "deepagent_deepseek"

    if model_name.startswith("gpt") or model_name.startswith("o1"):
        return "deepagent_openai"

    if "claude" in model_name or model_name.startswith("anthropic"):
        return "deepagent"

    return None


def resolve_token_limit(model_like: Any) -> int:
    """Resolve the effective context window for the provided model."""
    env_override = _read_int_from_env(_ENV_TOKEN_LIMIT_KEYS)
    if env_override is not None:
        return env_override

    if isinstance(model_like, BaseChatModel):
        attr_candidates = (
            "context_window",
            "max_context_tokens",
            "max_input_tokens",
            "max_total_tokens",
        )
        for attr in attr_candidates:
            value = getattr(model_like, attr, None)
            if isinstance(value, int) and value > 0:
                return value

        for attr in ("model_kwargs", "client_kwargs", "default_kwargs"):
            maybe_kwargs = getattr(model_like, attr, None)
            if isinstance(maybe_kwargs, dict):
                for key in (
                    "context_window",
                    "max_context_tokens",
                    "max_input_tokens",
                    "max_total_tokens",
                ):
                    candidate = maybe_kwargs.get(key)
                    if isinstance(candidate, int) and candidate > 0:
                        return candidate

        model_identifier = (
            getattr(model_like, "model_name", None)
            or getattr(model_like, "model", None)
            or getattr(model_like, "deployment_name", None)
        )
        if isinstance(model_identifier, str) and model_identifier.strip():
            return resolve_token_limit(model_identifier)

    if isinstance(model_like, str):
        normalized = model_like.strip().lower()
        if normalized in AGENT_LLM_MAP:
            llm_type = AGENT_LLM_MAP[normalized]
            return get_llm_token_limit_by_type(llm_type)

        # Allow provider-prefixed identifiers such as "openai:gpt-4o"
        if ":" in normalized:
            _, _, alias = normalized.partition(":")
            if alias and alias in AGENT_LLM_MAP:
                llm_type = AGENT_LLM_MAP[alias]
                return get_llm_token_limit_by_type(llm_type)

        inferred_type = _infer_llm_type_from_name(normalized)
        if inferred_type is not None:
            return get_llm_token_limit_by_type(inferred_type)

        return get_llm_token_limit_by_type(DEEPAGENT_LLM_TYPE)

    return get_llm_token_limit_by_type(DEEPAGENT_LLM_TYPE)


def compute_summary_budget(token_limit: int, requested: int | None = None) -> int:
    """Compute a safe summary budget for the given token limit."""
    if token_limit <= 0:
        return 4000

    safety_margin = max(int(token_limit * 0.1), 6000)
    max_threshold = token_limit - safety_margin
    if max_threshold <= 0:
        max_threshold = max(token_limit // 2, 2000)
    else:
        max_threshold = max(max_threshold, token_limit // 2, 2000)

    if requested is not None:
        return max(min(requested, max_threshold), 2000)

    return max_threshold


def determine_messages_to_keep(token_limit: int) -> int:
    """Determine how many recent messages to retain post-summarization."""
    if token_limit <= 60000:
        return 2
    if token_limit <= 150000:
        return 3
    if token_limit <= 220000:
        return 4
    return 6


def resolve_summary_parameters(
    model_like: Any,
    *,
    requested_summary_budget: int | None = None,
    allow_env_override: bool = True,
) -> tuple[int, int, int]:
    """Resolve (token_limit, summary_budget, messages_to_keep) for a model."""
    token_limit = resolve_token_limit(model_like)

    requested = requested_summary_budget
    if requested is None and allow_env_override:
        requested = _read_int_from_env(_ENV_SUMMARY_BUDGET_KEYS)

    summary_budget = compute_summary_budget(token_limit, requested)
    messages_to_keep = determine_messages_to_keep(token_limit)
    return token_limit, summary_budget, messages_to_keep


class AdaptiveSummarizationMiddleware(SummarizationMiddleware):
    """Summarization middleware with additional safeguards to keep context within budget."""

    def __init__(
        self,
        model: Any,
        max_tokens_before_summary: int | None,
        messages_to_keep: int,
        *,
        approx_chars_per_token: float = 3.2,
        token_budget_margin: float = 0.2,
        min_reserved_tokens: int = 768,
    ) -> None:
        super().__init__(
            model=model,
            max_tokens_before_summary=max_tokens_before_summary,
            messages_to_keep=messages_to_keep,
            token_counter=lambda msgs: count_tokens_approximately(
                msgs, chars_per_token=approx_chars_per_token
            ),
        )
        self.approx_chars_per_token = approx_chars_per_token
        self.token_budget_margin = token_budget_margin
        self.min_reserved_tokens = min_reserved_tokens

    def before_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:  # noqa: ARG002
        update = super().before_model(state, runtime)
        original_messages = list((update or {}).get("messages", state["messages"]))
        if not original_messages:
            return update

        sentinel_messages: list[RemoveMessage] = [
            msg for msg in original_messages if isinstance(msg, RemoveMessage)
        ]
        content_messages: list[AnyMessage] = [
            msg for msg in original_messages if not isinstance(msg, RemoveMessage)
        ]

        compressed_messages, changed = self._enforce_budget(content_messages)
        if not changed:
            return update

        if sentinel_messages:
            return {"messages": [*sentinel_messages, *compressed_messages]}
        return {"messages": compressed_messages}

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _enforce_budget(self, messages: list[AnyMessage]) -> tuple[list[AnyMessage], bool]:
        if self.max_tokens_before_summary is None:
            return messages, False

        pruned_messages = [m for m in messages if not isinstance(m, RemoveMessage)]
        total_tokens = self.token_counter(pruned_messages)
        if total_tokens <= self.max_tokens_before_summary:
            return messages, False

        normalized_messages = list(pruned_messages)
        if not normalized_messages:
            return normalized_messages, False

        last_human_idx = self._find_last_human_index(normalized_messages)
        preserve_flags = [False] * len(normalized_messages)
        tokens_reserved = 0

        if last_human_idx is not None:
            normalized_messages[last_human_idx] = self._truncate_if_needed(
                normalized_messages[last_human_idx],
                self._max_preservable_tokens(),
            )
            preserve_flags[last_human_idx] = True
            tokens_reserved = self.token_counter(
                [normalized_messages[last_human_idx]]
            )

        available_budget = self._max_preservable_tokens()
        for idx in range(len(normalized_messages) - 1, -1, -1):
            if preserve_flags[idx]:
                continue
            message = normalized_messages[idx]
            message_tokens = self.token_counter([message])

            if tokens_reserved + message_tokens <= available_budget:
                preserve_flags[idx] = True
                tokens_reserved += message_tokens

        balanced_messages = self._rebalance_until_within_budget(
            normalized_messages,
            preserve_flags,
            last_human_idx,
        )
        balanced_messages = self._drop_orphan_tool_pairs(balanced_messages)
        self._ensure_message_ids(balanced_messages)
        return balanced_messages, balanced_messages != messages

    def _rebalance_until_within_budget(
        self,
        normalized_messages: list[AnyMessage],
        preserve_flags: list[bool],
        last_human_idx: int | None,
    ) -> list[AnyMessage]:
        if self.max_tokens_before_summary is None:
            return normalized_messages

        clusters = self._collect_message_clusters(normalized_messages)
        self._synchronize_tool_preservation(clusters, preserve_flags)
        current = self._assemble_messages(normalized_messages, preserve_flags)

        while self.token_counter(current) > self.max_tokens_before_summary:
            drop_cluster = self._select_drop_cluster(
                clusters, preserve_flags, last_human_idx
            )
            if not drop_cluster:
                break
            for idx in drop_cluster:
                preserve_flags[idx] = False
            clusters = self._collect_message_clusters(normalized_messages)
            self._synchronize_tool_preservation(clusters, preserve_flags)
            current = self._assemble_messages(normalized_messages, preserve_flags)

        if self.token_counter(current) <= self.max_tokens_before_summary:
            return current

        if last_human_idx is not None and preserve_flags[last_human_idx]:
            normalized_messages[last_human_idx] = self._truncate_if_needed(
                normalized_messages[last_human_idx],
                max(self.min_reserved_tokens, self.max_tokens_before_summary // 4),
            )
            clusters = self._collect_message_clusters(normalized_messages)
            self._synchronize_tool_preservation(clusters, preserve_flags)
            current = self._assemble_messages(normalized_messages, preserve_flags)
            if self.token_counter(current) <= self.max_tokens_before_summary:
                return current

        trailing_messages: list[AnyMessage] = []
        if last_human_idx is not None:
            trailing_messages = [normalized_messages[last_human_idx]]
            summary_source = [
                normalized_messages[i]
                for i in range(len(normalized_messages))
                if i != last_human_idx
            ]
        else:
            summary_source = list(normalized_messages)

        summary_text = self._create_summary(summary_source)
        summary_messages = self._build_new_messages(summary_text)
        collapsed = [*summary_messages, *trailing_messages]

        if (
            self.token_counter(collapsed) > self.max_tokens_before_summary
            and trailing_messages
        ):
            collapsed = summary_messages
        return collapsed

    def _collect_message_clusters(
        self, messages: list[AnyMessage]
    ) -> list[dict[str, Any]]:
        clusters: list[dict[str, Any]] = []
        visited: set[int] = set()

        for idx, message in enumerate(messages):
            if idx in visited:
                continue

            if isinstance(message, AIMessage) and getattr(message, "tool_calls", None):
                tool_ids = self._extract_tool_call_ids(message)
                cluster_indices = [idx]
                visited.add(idx)
                missing_ids = set(tool_ids)

                j = idx + 1
                while j < len(messages) and missing_ids:
                    next_message = messages[j]
                    if isinstance(next_message, ToolMessage):
                        if next_message.tool_call_id in missing_ids:
                            cluster_indices.append(j)
                            visited.add(j)
                            missing_ids.remove(next_message.tool_call_id)
                            j += 1
                            continue
                        j += 1
                        continue
                    break

                clusters.append(
                    {"indices": sorted(cluster_indices), "missing": missing_ids}
                )
                continue

            visited.add(idx)
            clusters.append({"indices": [idx], "missing": set()})

        clusters.sort(key=lambda entry: entry["indices"][0])
        return clusters

    def _synchronize_tool_preservation(
        self,
        clusters: list[dict[str, Any]],
        preserve_flags: list[bool],
    ) -> None:
        for cluster in clusters:
            indices = cluster["indices"]
            if cluster["missing"]:
                for idx in indices:
                    preserve_flags[idx] = False
                continue
            should_preserve = any(preserve_flags[idx] for idx in indices)
            if should_preserve != all(preserve_flags[idx] for idx in indices):
                for idx in indices:
                    preserve_flags[idx] = should_preserve

    def _select_drop_cluster(
        self,
        clusters: list[dict[str, Any]],
        preserve_flags: list[bool],
        last_human_idx: int | None,
    ) -> list[int] | None:
        for cluster in clusters:
            indices = cluster["indices"]
            if cluster["missing"]:
                continue
            if last_human_idx is not None and last_human_idx in indices:
                continue
            if all(preserve_flags[idx] for idx in indices):
                return indices
        return None

    def _assemble_messages(
        self,
        normalized_messages: list[AnyMessage],
        preserve_flags: list[bool],
    ) -> list[AnyMessage]:
        summary_indices = [i for i, keep in enumerate(preserve_flags) if not keep]
        preserved_indices = [i for i, keep in enumerate(preserve_flags) if keep]

        summary_messages: list[AnyMessage] = []
        if summary_indices:
            summary_source = [normalized_messages[i] for i in summary_indices]
            summary_text = self._create_summary(summary_source)
            summary_messages = self._build_new_messages(summary_text)

        preserved_messages = [normalized_messages[i] for i in preserved_indices]
        return [*summary_messages, *preserved_messages]

    def _drop_orphan_tool_pairs(self, messages: list[AnyMessage]) -> list[AnyMessage]:
        cleaned: list[AnyMessage] = []
        pending_tool_ids: set[str] = set()
        cluster_start_index: int | None = None

        for message in messages:
            if isinstance(message, AIMessage) and getattr(message, "tool_calls", None):
                if pending_tool_ids and cluster_start_index is not None:
                    cleaned = cleaned[:cluster_start_index]
                pending_tool_ids = self._extract_tool_call_ids(message)
                cluster_start_index = len(cleaned)
                cleaned.append(message)
                if not pending_tool_ids:
                    cluster_start_index = None
                continue

            if isinstance(message, ToolMessage):
                if pending_tool_ids and message.tool_call_id in pending_tool_ids:
                    cleaned.append(message)
                    pending_tool_ids.remove(message.tool_call_id)
                    if not pending_tool_ids:
                        cluster_start_index = None
                continue

            if pending_tool_ids and cluster_start_index is not None:
                cleaned = cleaned[:cluster_start_index]
            pending_tool_ids.clear()
            cluster_start_index = None
            cleaned.append(message)

        if pending_tool_ids and cluster_start_index is not None:
            cleaned = cleaned[:cluster_start_index]

        return cleaned

    def _max_preservable_tokens(self) -> int:
        if self.max_tokens_before_summary is None:
            return 0
        reserved = max(
            self.min_reserved_tokens,
            int(self.max_tokens_before_summary * self.token_budget_margin),
        )
        baseline = max(self.max_tokens_before_summary // 2, 1)
        return max(self.max_tokens_before_summary - reserved, baseline)

    def _truncate_if_needed(
        self,
        message: AnyMessage,
        target_tokens: int,
    ) -> AnyMessage:
        target_tokens = max(target_tokens, 1)
        current_tokens = self.token_counter([message])
        if current_tokens <= target_tokens:
            return message

        content_text = self._stringify_message_content(message)
        if not content_text:
            return message

        max_chars = max(int(target_tokens * self.approx_chars_per_token), 32)
        truncated = content_text[:max_chars].rsplit(" ", 1)[0].strip()
        if not truncated:
            truncated = content_text[:max_chars]

        omitted = len(content_text) - len(truncated)
        truncated += (
            f"\n\n[Context truncated to preserve window. "
            f"Omitted approximately {omitted} characters.]"
        )

        additional = dict(getattr(message, "additional_kwargs", {}) or {})
        additional.update(
            {
                "context_truncated": True,
                "context_original_chars": len(content_text),
                "context_omitted_chars": max(omitted, 0),
            }
        )

        try:
            return message.model_copy(
                update={"content": truncated, "additional_kwargs": additional}
            )
        except Exception:  # noqa: BLE001
            return HumanMessage(
                content=truncated,
                additional_kwargs=additional,
            )

    def _stringify_message_content(self, message: AnyMessage) -> str:
        content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict):
                    text = block.get("text")
                    if isinstance(text, str):
                        parts.append(text)
                    else:
                        parts.append(str(block))
                else:
                    parts.append(str(block))
            return "\n".join(parts)
        return str(content)

    def _find_last_human_index(self, messages: list[AnyMessage]) -> int | None:
        for idx in range(len(messages) - 1, -1, -1):
            if isinstance(messages[idx], HumanMessage):
                return idx
        return None


__all__ = [
    "AdaptiveSummarizationMiddleware",
    "compute_summary_budget",
    "determine_messages_to_keep",
    "resolve_summary_parameters",
    "resolve_token_limit",
]
