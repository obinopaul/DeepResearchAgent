"""DeepAgents implemented as Middleware"""

from src.agents.agents import create_agent
from src.agents.agents.middleware import AgentMiddleware, ModelRequest, SummarizationMiddleware
from src.agents.agents.utils.runtime import Runtime
from src.agents.agents.middleware.types import AgentState
from src.agents.agents.middleware.prompt_caching import AnthropicPromptCachingMiddleware
from langchain_core.tools import BaseTool, tool, InjectedToolCallId
from langchain_core.messages import ToolMessage, AnyMessage, HumanMessage, RemoveMessage, AIMessage
from langchain_core.language_models.chat_models import BaseChatModel
from langchain.chat_models import init_chat_model
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.types import Command
from src.agents.agents.tools.tool_node import InjectedState
from typing import Annotated, Any
from src.agents.deep_agents.state import PlanningState, FilesystemState, DeepAgentState
from src.agents.deep_agents.tools import write_todos, ls, read_file, write_file, edit_file
from src.agents.deep_agents.prompts import (
    WRITE_TODOS_SYSTEM_PROMPT,
    TASK_SYSTEM_PROMPT,
    FILESYSTEM_SYSTEM_PROMPT,
    TASK_TOOL_DESCRIPTION,
    BASE_AGENT_PROMPT,
    INSIGHT_LOGGING_SYSTEM_PROMPT,
)
from src.agents.deep_agents.types import SubAgent, CustomSubAgent
from src.llms.llm import get_llm_token_limit_by_type
from src.config.agents import AGENT_LLM_MAP, DEEPAGENT_LLM_TYPE


def _resolve_token_limit_for_model(model_like) -> int:
    if isinstance(model_like, str):
        return get_llm_token_limit_by_type(model_like)
    if isinstance(model_like, BaseChatModel):
        attr_candidates = (
            "max_input_tokens",
            "max_total_tokens",
            "max_context_tokens",
            "max_tokens",
        )
        for attr in attr_candidates:
            value = getattr(model_like, attr, None)
            if isinstance(value, int) and value > 0:
                return value
        for attr in ("model_kwargs", "client_kwargs", "default_kwargs"):
            maybe_kwargs = getattr(model_like, attr, None)
            if isinstance(maybe_kwargs, dict):
                for key in (
                    "max_tokens",
                    "max_input_tokens",
                    "max_total_tokens",
                    "max_output_tokens",
                ):
                    candidate = maybe_kwargs.get(key)
                    if isinstance(candidate, int) and candidate > 0:
                        return candidate
    return get_llm_token_limit_by_type(DEEPAGENT_LLM_TYPE)


def _compute_summary_budget(token_limit: int, requested: int | None = None) -> int:
    if requested is not None:
        capped = min(requested, max(token_limit - 8000, 4000))
        return max(capped, 2000)
    budget = max(token_limit // 20, 4000)
    return min(budget, max(token_limit - 8000, 4000))


def _determine_messages_to_keep(token_limit: int) -> int:
    if token_limit <= 60000:
        return 2
    if token_limit <= 150000:
        return 3
    if token_limit <= 220000:
        return 4
    return 6


def build_deepagent_middleware_stack(model, summary_budget: int) -> list[AgentMiddleware]:
    token_limit = _resolve_token_limit_for_model(model)
    messages_to_keep = _determine_messages_to_keep(token_limit)
    return [
        PlanningMiddleware(),
        FilesystemMiddleware(),
        InsightLoggingMiddleware(),
        AdaptiveSummarizationMiddleware(
            model=model,
            max_tokens_before_summary=summary_budget,
            messages_to_keep=messages_to_keep,
        ),
        AnthropicPromptCachingMiddleware(ttl="5m", unsupported_model_behavior="ignore"),
    ]

###########################
# Planning Middleware
###########################

class PlanningMiddleware(AgentMiddleware):
    state_schema = PlanningState
    tools = [write_todos]

    def __init__(self) -> None:
        super().__init__()
        self.name = "PlanningMiddleware"

    def modify_model_request(self, request: ModelRequest, agent_state: PlanningState, runtime: Runtime) -> ModelRequest:
        request.system_prompt = request.system_prompt + "\n\n" + WRITE_TODOS_SYSTEM_PROMPT
        return request

###########################
# Filesystem Middleware
###########################

class FilesystemMiddleware(AgentMiddleware):
    state_schema = FilesystemState
    tools = [ls, read_file, write_file, edit_file]

    def __init__(self) -> None:
        super().__init__()
        self.name = "FilesystemMiddleware"
        
    def modify_model_request(self, request: ModelRequest, agent_state: FilesystemState, runtime: Runtime) -> ModelRequest:
        request.system_prompt = request.system_prompt + "\n\n" + FILESYSTEM_SYSTEM_PROMPT
        return request

###########################
# Insight Logging Middleware
###########################

class InsightLoggingMiddleware(AgentMiddleware):
    state_schema = DeepAgentState

    def __init__(self) -> None:
        super().__init__()
        self.name = "InsightLoggingMiddleware"

    def modify_model_request(self, request: ModelRequest, agent_state: DeepAgentState, runtime: Runtime) -> ModelRequest:
        request.system_prompt = request.system_prompt + "\n\n" + INSIGHT_LOGGING_SYSTEM_PROMPT
        return request


class AdaptiveSummarizationMiddleware(SummarizationMiddleware):
    """Summarization middleware with additional safeguards to keep context within budget.

    This wraps the base SummarizationMiddleware behaviour and adds a second-stage
    compaction pass that aggressively compresses history (while preserving the latest
    human intent) whenever the conversation still exceeds the configured budget.
    """

    def __init__(
        self,
        model,
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

    def before_model(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
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

    # --------------------------------------------------------------------- #
    # Internal helpers
    # --------------------------------------------------------------------- #

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
        # Reserve from the newest messages backwards
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

        # Attempt to further compress the last human message if needed
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

        # Final fallback: collapse everything into a single summary,
        # optionally followed by the final human message.
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
                # Drop orphan tool messages silently
                continue

            # Any other message breaks pending tool chains
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
            # Fallback to constructing a plain HumanMessage compatible object.
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

###########################
# SubAgent Middleware
###########################

class SubAgentMiddleware(AgentMiddleware):
    def __init__(
        self,
        default_subagent_tools: list[BaseTool] = [],
        subagents: list[SubAgent | CustomSubAgent] = [],
        model=None,
        is_async=False,
        summary_budget: int | None = None,
    ) -> None:
        super().__init__()
        self.name = "SubAgentMiddleware"
        task_tool = create_task_tool(
            default_subagent_tools=default_subagent_tools,
            subagents=subagents,
            model=model,
            is_async=is_async,
            summary_budget=summary_budget,
        )
        self.tools = [task_tool]

    def modify_model_request(self, request: ModelRequest, agent_state: AgentState, runtime: Runtime) -> ModelRequest:
        request.system_prompt = request.system_prompt + "\n\n" + TASK_SYSTEM_PROMPT
        return request

def _get_agents(
    default_subagent_tools: list[BaseTool],
    subagents: list[SubAgent | CustomSubAgent],
    model,
    summary_budget: int | None,
):
    if summary_budget is None:
        llm_token_limit = _resolve_token_limit_for_model(model)
        summary_budget = _compute_summary_budget(llm_token_limit)
    else:
        llm_token_limit = _resolve_token_limit_for_model(model)
        summary_budget = _compute_summary_budget(llm_token_limit, summary_budget)

    messages_to_keep = _determine_messages_to_keep(llm_token_limit)

    default_subagent_middleware = build_deepagent_middleware_stack(model, summary_budget)
    agents = {
        "general-purpose": create_agent(
            model,
            prompt=BASE_AGENT_PROMPT,
            tools=default_subagent_tools,
            checkpointer=False,
            middleware=default_subagent_middleware
        )
    }
    for _agent in subagents:
        if "graph" in _agent:
            agents[_agent["name"]] = _agent["graph"]
            continue
        if "tools" in _agent:
            _tools = _agent["tools"]
        else:
            _tools = default_subagent_tools.copy()
        # Resolve per-subagent model: can be instance or dict
        if "model" in _agent:
            agent_model = _agent["model"]
            if isinstance(agent_model, dict):
                # Dictionary settings - create model from config
                sub_model = init_chat_model(**agent_model)
            else:
                # Model instance - use directly
                sub_model = agent_model
        else:
            # Fallback to main model
            sub_model = model
        sub_summary_budget = _compute_summary_budget(
            _resolve_token_limit_for_model(sub_model),
            _agent.get("summary_budget"),
        )
        sub_default_middleware = build_deepagent_middleware_stack(
            sub_model,
            sub_summary_budget,
        )
        if "middleware" in _agent:
            _middleware = [*sub_default_middleware, *_agent["middleware"]]
        else:
            _middleware = sub_default_middleware
        agents[_agent["name"]] = create_agent(
            sub_model,
            prompt=_agent["prompt"],
            tools=_tools,
            middleware=_middleware,
            checkpointer=False,
        )
    return agents


def _get_subagent_description(subagents: list[SubAgent | CustomSubAgent]):
    return [f"- {_agent['name']}: {_agent['description']}" for _agent in subagents]


def create_task_tool(
    default_subagent_tools: list[BaseTool],
    subagents: list[SubAgent | CustomSubAgent],
    model,
    is_async: bool = False,
    summary_budget: int | None = None,
):
    agents = _get_agents(
        default_subagent_tools, subagents, model, summary_budget
    )
    other_agents_string = _get_subagent_description(subagents)

    if is_async:
        @tool(
            description=TASK_TOOL_DESCRIPTION.format(other_agents=other_agents_string)
        )
        async def task(
            description: str,
            subagent_type: str,
            state: Annotated[dict, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
        ):
            if subagent_type not in agents:
                return f"Error: invoked agent of type {subagent_type}, the only allowed types are {[f'`{k}`' for k in agents]}"
            sub_agent = agents[subagent_type]
            state["messages"] = [{"role": "user", "content": description}]
            result = await sub_agent.ainvoke(state)
            state_update = {}
            for k, v in result.items():
                if k not in ["todos", "messages"]:
                    state_update[k] = v
            return Command(
                update={
                    **state_update,
                    "messages": [
                        ToolMessage(
                            result["messages"][-1].content, tool_call_id=tool_call_id
                        )
                    ],
                }
            )
    else: 
        @tool(
            description=TASK_TOOL_DESCRIPTION.format(other_agents=other_agents_string)
        )
        def task(
            description: str,
            subagent_type: str,
            state: Annotated[dict, InjectedState],
            tool_call_id: Annotated[str, InjectedToolCallId],
        ):
            if subagent_type not in agents:
                return f"Error: invoked agent of type {subagent_type}, the only allowed types are {[f'`{k}`' for k in agents]}"
            sub_agent = agents[subagent_type]
            state["messages"] = [{"role": "user", "content": description}]
            result = sub_agent.invoke(state)
            state_update = {}
            for k, v in result.items():
                if k not in ["todos", "messages"]:
                    state_update[k] = v
            return Command(
                update={
                    **state_update,
                    "messages": [
                        ToolMessage(
                            result["messages"][-1].content, tool_call_id=tool_call_id
                        )
                    ],
                }
            )
    return task
