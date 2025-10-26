"""Timer middleware for deep agents."""

from __future__ import annotations

import time
from typing import Any

from langchain_core.messages import HumanMessage

from src.agents.agents.middleware.types import AgentMiddleware, AgentState
from src.agents.agents.utils.runtime import Runtime


class ResearchTimerMiddleware(AgentMiddleware[AgentState, Any]):
    """Injects wrap-up instructions as the research timer approaches its limit."""

    def __init__(
        self,
        *,
        total_seconds: float,
        warning_ratio: float = 0.75,
        warning_offset_seconds: float = 60.0,
        round_up_message: str | None = None,
        final_message: str | None = None,
    ) -> None:
        if total_seconds <= 0:
            raise ValueError("total_seconds must be positive")

        self.total_seconds = float(total_seconds)
        self.warning_ratio = warning_ratio
        self.warning_offset_seconds = max(warning_offset_seconds, 0.0)
        self.round_up_message = (
            round_up_message
            or "Time check: about {remaining} remaining. Transition into summarizing key findings and prepare the final response."
        )
        self.final_message = (
            final_message
            or "The research timer has elapsed. Deliver a concise final summary that is detailed and extensive, highlighting the most important insights and next steps."
        )

        self._start_time: float | None = None
        self._warning_sent = False
        self._final_sent = False

        # Warning threshold occurs at the earlier of 75% elapsed or one minute remaining.
        ratio_threshold = self.total_seconds * max(self.warning_ratio, 0.0)
        minute_threshold = (
            self.total_seconds - self.warning_offset_seconds
            if self.total_seconds > self.warning_offset_seconds
            else self.total_seconds
        )
        # Guard against negative thresholds; warning at time zero is harmless.
        self._warning_deadline = max(min(ratio_threshold, minute_threshold), 0.0)
        self.name = "ResearchTimerMiddleware"
        self.tools: list[Any] = []

    def before_model(self, state: AgentState, runtime: Runtime[Any]) -> dict[str, Any] | None:  # noqa: ARG002
        now = time.monotonic()
        if self._start_time is None:
            self._start_time = now
            return None

        elapsed = now - self._start_time
        updates: dict[str, Any] | None = None

        if not self._final_sent and elapsed >= self.total_seconds:
            updates = self._append_message(state, self.final_message)
            self._final_sent = True
            self._warning_sent = True
        elif not self._warning_sent and elapsed >= self._warning_deadline:
            remaining = max(self.total_seconds - elapsed, 0.0)
            remaining_str = self._format_remaining(remaining)
            updates = self._append_message(
                state, self.round_up_message.format(remaining=remaining_str)
            )
            self._warning_sent = True

        return updates

    def _append_message(self, state: AgentState, content: str) -> dict[str, Any]:
        messages = list(state["messages"])
        if messages and isinstance(messages[-1], HumanMessage):
            last_content = messages[-1].content
            if isinstance(last_content, str) and last_content.strip() == content.strip():
                return None
        messages.append(HumanMessage(content=content, name="timer"))
        return {"messages": messages}

    @staticmethod
    def _format_remaining(seconds: float) -> str:
        bounded = max(seconds, 0.0)
        if bounded >= 90:
            minutes = int(round(bounded / 60))
            return f"{minutes} minute{'s' if minutes != 1 else ''}"
        if bounded >= 60:
            whole_minutes = int(bounded // 60)
            remainder = int(bounded % 60)
            if remainder == 0:
                return f"{whole_minutes} minute{'s' if whole_minutes != 1 else ''}"
            return f"{whole_minutes} minute{'s' if whole_minutes != 1 else ''} and {remainder} second{'s' if remainder != 1 else ''}"
        seconds_int = max(int(round(bounded)), 1)
        return f"{seconds_int} second{'s' if seconds_int != 1 else ''}"
