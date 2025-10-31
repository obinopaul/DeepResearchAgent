import importlib
import sys
from typing import Any

import pytest

try:
    # from langchain.agents import create_agent
    from src.agents.agents import create_agent
except Exception as exc:  # noqa: BLE001 - broad to catch pydantic evaluation errors on py3.14
    create_agent = None  # type: ignore[assignment]
    _LANGCHAIN_IMPORT_ERROR = exc
else:
    _LANGCHAIN_IMPORT_ERROR = None
from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolCall,
    ToolMessage,
)
from langchain_core.tools import BaseTool
from langgraph.graph.message import add_messages
from langgraph.managed import RemainingSteps
from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from src.agents.deep_agents.middleware.filesystem import (
    FILESYSTEM_SYSTEM_PROMPT,
    FILESYSTEM_SYSTEM_PROMPT_LONGTERM_SUPPLEMENT,
    FileData,
    FilesystemMiddleware,
    FilesystemState,
)
from src.agents.deep_agents.middleware.patch_tool_calls import PatchToolCallsMiddleware
from src.agents.deep_agents.middleware.subagents import (
    DEFAULT_GENERAL_PURPOSE_DESCRIPTION,
    TASK_SYSTEM_PROMPT,
    TASK_TOOL_DESCRIPTION,
    SubAgentMiddleware,
)
from src.agents.agents.tools.tool_node import ToolRuntime
from src.agents.agents.utils.runtime import Runtime
from src.agents.deep_agents.middleware.timer import ResearchTimerMiddleware


class TestAddMiddleware:
    def test_filesystem_middleware(self):
        if create_agent is None:
            pytest.skip(f"create_agent unavailable: {_LANGCHAIN_IMPORT_ERROR}")
        middleware = [FilesystemMiddleware()]
        agent = create_agent(model="claude-sonnet-4-20250514", middleware=middleware, tools=[])
        assert "files" in agent.stream_channels
        agent_tools = agent.nodes["tools"].bound._tools_by_name.keys()
        assert "ls" in agent_tools
        assert "read_file" in agent_tools
        assert "write_file" in agent_tools
        assert "edit_file" in agent_tools

    def test_subagent_middleware(self):
        if create_agent is None:
            pytest.skip(f"create_agent unavailable: {_LANGCHAIN_IMPORT_ERROR}")
        middleware = [SubAgentMiddleware(default_tools=[], subagents=[], default_model="claude-sonnet-4-20250514")]
        agent = create_agent(model="claude-sonnet-4-20250514", middleware=middleware, tools=[])
        assert "task" in agent.nodes["tools"].bound._tools_by_name.keys()

    def test_multiple_middleware(self):
        if create_agent is None:
            pytest.skip(f"create_agent unavailable: {_LANGCHAIN_IMPORT_ERROR}")
        middleware = [FilesystemMiddleware(), SubAgentMiddleware(default_tools=[], subagents=[], default_model="claude-sonnet-4-20250514")]
        agent = create_agent(model="claude-sonnet-4-20250514", middleware=middleware, tools=[])
        assert "files" in agent.stream_channels
        agent_tools = agent.nodes["tools"].bound._tools_by_name.keys()
        assert "ls" in agent_tools
        assert "read_file" in agent_tools
        assert "write_file" in agent_tools
        assert "edit_file" in agent_tools
        assert "task" in agent_tools


class TestFilesystemMiddleware:
    def test_init_local(self):
        middleware = FilesystemMiddleware(long_term_memory=False)
        assert middleware.long_term_memory is False
        assert middleware.system_prompt == FILESYSTEM_SYSTEM_PROMPT
        assert len(middleware.tools) == 4

    def test_init_longterm(self):
        middleware = FilesystemMiddleware(long_term_memory=True)
        assert middleware.long_term_memory is True
        assert middleware.system_prompt == (FILESYSTEM_SYSTEM_PROMPT + FILESYSTEM_SYSTEM_PROMPT_LONGTERM_SUPPLEMENT)
        assert len(middleware.tools) == 4

    def test_init_custom_system_prompt_shortterm(self):
        middleware = FilesystemMiddleware(long_term_memory=False, system_prompt="Custom system prompt")
        assert middleware.long_term_memory is False
        assert middleware.system_prompt == "Custom system prompt"
        assert len(middleware.tools) == 4

    def test_init_custom_system_prompt_longterm(self):
        middleware = FilesystemMiddleware(long_term_memory=True, system_prompt="Custom system prompt")
        assert middleware.long_term_memory is True
        assert middleware.system_prompt == "Custom system prompt"
        assert len(middleware.tools) == 4

    def test_init_custom_tool_descriptions_shortterm(self):
        middleware = FilesystemMiddleware(long_term_memory=False, custom_tool_descriptions={"ls": "Custom ls tool description"})
        assert middleware.long_term_memory is False
        assert middleware.system_prompt == FILESYSTEM_SYSTEM_PROMPT
        ls_tool = next(tool for tool in middleware.tools if tool.name == "ls")
        assert ls_tool.description == "Custom ls tool description"

    def test_init_custom_tool_descriptions_longterm(self):
        middleware = FilesystemMiddleware(long_term_memory=True, custom_tool_descriptions={"ls": "Custom ls tool description"})
        assert middleware.long_term_memory is True
        assert middleware.system_prompt == (FILESYSTEM_SYSTEM_PROMPT + FILESYSTEM_SYSTEM_PROMPT_LONGTERM_SUPPLEMENT)
        ls_tool = next(tool for tool in middleware.tools if tool.name == "ls")
        assert ls_tool.description == "Custom ls tool description"

    def test_ls_shortterm(self):
        state = FilesystemState(
            messages=[],
            files={
                "test.txt": FileData(
                    content=["Hello world"],
                    modified_at="2021-01-01",
                    created_at="2021-01-01",
                ),
                "test2.txt": FileData(
                    content=["Goodbye world"],
                    modified_at="2021-01-01",
                    created_at="2021-01-01",
                ),
            },
        )
        middleware = FilesystemMiddleware(long_term_memory=False)
        ls_tool = next(tool for tool in middleware.tools if tool.name == "ls")
        result = ls_tool.invoke(
            {"runtime": ToolRuntime(state=state, context=None, tool_call_id="", store=None, stream_writer=lambda _: None, config={})}
        )
        assert result == ["test.txt", "test2.txt"]

    def test_ls_shortterm_with_path(self):
        state = FilesystemState(
            messages=[],
            files={
                "/test.txt": FileData(
                    content=["Hello world"],
                    modified_at="2021-01-01",
                    created_at="2021-01-01",
                ),
                "/pokemon/test2.txt": FileData(
                    content=["Goodbye world"],
                    modified_at="2021-01-01",
                    created_at="2021-01-01",
                ),
                "/pokemon/charmander.txt": FileData(
                    content=["Ember"],
                    modified_at="2021-01-01",
                    created_at="2021-01-01",
                ),
                "/pokemon/water/squirtle.txt": FileData(
                    content=["Water"],
                    modified_at="2021-01-01",
                    created_at="2021-01-01",
                ),
            },
        )
        middleware = FilesystemMiddleware(long_term_memory=False)
        ls_tool = next(tool for tool in middleware.tools if tool.name == "ls")
        result = ls_tool.invoke(
            {
                "path": "pokemon/",
                "runtime": ToolRuntime(state=state, context=None, tool_call_id="", store=None, stream_writer=lambda _: None, config={}),
            }
        )
        assert "/pokemon/test2.txt" in result
        assert "/pokemon/charmander.txt" in result

    def test_ls_runtime_excluded_from_schema(self):
        middleware = FilesystemMiddleware(long_term_memory=False)
        ls_tool = next(tool for tool in middleware.tools if tool.name == "ls")
        schema = ls_tool.args_schema.schema()
        assert "runtime" not in schema.get("required", [])

    def test_read_file_runtime_excluded_from_schema(self):
        middleware = FilesystemMiddleware(long_term_memory=False)
        read_tool = next(tool for tool in middleware.tools if tool.name == "read_file")
        schema = read_tool.args_schema.schema()
        assert "runtime" not in schema.get("required", [])

    def test_ls_handles_missing_runtime(self):
        middleware = FilesystemMiddleware(long_term_memory=False)
        ls_tool = next(tool for tool in middleware.tools if tool.name == "ls")
        assert ls_tool.invoke({"runtime": None}) == "Filesystem runtime unavailable"

    def test_read_file_handles_missing_runtime(self):
        middleware = FilesystemMiddleware(long_term_memory=False)
        read_tool = next(tool for tool in middleware.tools if tool.name == "read_file")
        result = read_tool.invoke({"file_path": "test.txt", "runtime": None})
        assert result == "Error: Filesystem runtime unavailable"


def _make_state(*, files: dict[str, FileData] | None = None) -> FilesystemState:
    return FilesystemState(messages=[], files=files or {})


def _make_runtime(
    state: FilesystemState,
    *,
    store: InMemoryStore | None = None,
    tool_call_id: str | None = "test-call",
) -> ToolRuntime:
    return ToolRuntime(
        state=state,
        context=None,
        config={},
        stream_writer=lambda _chunk: None,
        tool_call_id=tool_call_id,
        store=store,
    )


def _apply_command(state: FilesystemState, command: Command) -> None:
    update = command.update
    if update is None:
        return
    files_update = update.get("files")
    if files_update:
        files = dict(state.get("files", {}))
        files.update(files_update)
        state["files"] = files
    messages_update = update.get("messages")
    if messages_update:
        state_messages = list(state.get("messages", []))
        state_messages.extend(messages_update)
        state["messages"] = state_messages


def _file_data(content: str) -> FileData:
    return FileData(
        content=content.split("\n"),
        created_at="2024-01-01T00:00:00+00:00",
        modified_at="2024-01-01T00:00:00+00:00",
    )


def _ensure_tool_schema(tool: BaseTool) -> None:
    args_schema = getattr(tool, "args_schema", None)
    rebuild = getattr(args_schema, "model_rebuild", None)
    if callable(rebuild):
        module_names = {
            name
            for name in (tool.__module__, getattr(args_schema, "__module__", None), "src.agents.agents.middleware.types")
            if name
        }
        namespace: dict[str, Any] = {}
        for module_name in module_names:
            try:
                module = importlib.import_module(module_name)
            except Exception:  # noqa: BLE001 - best-effort loading for schema rebuild
                module = sys.modules.get(module_name)
            if module is not None:
                namespace.update(vars(module))
        namespace.setdefault("BaseMessage", BaseMessage)
        namespace.setdefault("add_messages", add_messages)
        namespace.setdefault("RemainingSteps", RemainingSteps)
        rebuild(_types_namespace=namespace)


class TestFilesystemToolExecution:
    def test_short_term_full_tool_cycle(self) -> None:
        middleware = FilesystemMiddleware(long_term_memory=False)
        tools = {tool.name: tool for tool in middleware.tools}
        for tool in tools.values():
            _ensure_tool_schema(tool)
        state = _make_state()

        write_result = tools["write_file"].invoke(
            {
                "file_path": "/notes.txt",
                "content": "First line",
                "runtime": _make_runtime(state, tool_call_id="write-1"),
            }
        )
        assert isinstance(write_result, Command)
        _apply_command(state, write_result)

        ls_output = tools["ls"].invoke({"runtime": _make_runtime(state)})
        assert isinstance(ls_output, list)
        assert "/notes.txt" in ls_output

        read_output = tools["read_file"].invoke({"file_path": "/notes.txt", "runtime": _make_runtime(state)})
        assert "First line" in read_output

        edit_result = tools["edit_file"].invoke(
            {
                "file_path": "/notes.txt",
                "old_string": "First line",
                "new_string": "Updated line",
                "runtime": _make_runtime(state, tool_call_id="edit-1"),
            }
        )
        assert isinstance(edit_result, Command)
        _apply_command(state, edit_result)

        read_after_edit = tools["read_file"].invoke({"file_path": "/notes.txt", "runtime": _make_runtime(state)})
        assert "Updated line" in read_after_edit

    def test_long_term_tool_cycle(self) -> None:
        middleware = FilesystemMiddleware(long_term_memory=True)
        tools = {tool.name: tool for tool in middleware.tools}
        for tool in tools.values():
            _ensure_tool_schema(tool)
        state = _make_state(files={"/local.txt": _file_data("Local entry")})
        store = InMemoryStore()
        store.put(("filesystem",), "/archive.txt", {
            "content": ["Stored"],
            "created_at": "2024-01-01T00:00:00+00:00",
            "modified_at": "2024-01-01T00:00:00+00:00",
        })

        ls_output = tools["ls"].invoke({"runtime": _make_runtime(state, store=store)})
        assert isinstance(ls_output, list)
        assert "/local.txt" in ls_output
        assert "/memories/archive.txt" in ls_output

        read_store = tools["read_file"].invoke(
            {
                "file_path": "/memories/archive.txt",
                "runtime": _make_runtime(state, store=store),
            }
        )
        assert "Stored" in read_store

        write_result = tools["write_file"].invoke(
            {
                "file_path": "/memories/journal.txt",
                "content": "Journal entry",
                "runtime": _make_runtime(state, store=store, tool_call_id="write-long"),
            }
        )
        assert isinstance(write_result, str)
        journal_item = store.get(("filesystem",), "/journal.txt")
        assert journal_item is not None
        assert "Journal entry" in "\n".join(journal_item.value["content"])

        store.put(("filesystem",), "/journal.txt", {
            "content": ["Journal entry"],
            "created_at": "2024-01-01T00:00:00+00:00",
            "modified_at": "2024-01-01T00:00:00+00:00",
        })
        edit_output = tools["edit_file"].invoke(
            {
                "file_path": "/memories/journal.txt",
                "old_string": "Journal entry",
                "new_string": "Updated journal",
                "runtime": _make_runtime(state, store=store, tool_call_id="edit-long"),
            }
        )
        assert isinstance(edit_output, str)
        updated_item = store.get(("filesystem",), "/journal.txt")
        assert updated_item is not None
        assert "Updated journal" in "\n".join(updated_item.value["content"])

    def test_long_term_tools_require_store(self) -> None:
        middleware = FilesystemMiddleware(long_term_memory=True)
        ls_tool = next(tool for tool in middleware.tools if tool.name == "ls")
        _ensure_tool_schema(ls_tool)
        state = _make_state()
        with pytest.raises(ValueError):
            ls_tool.invoke({"runtime": _make_runtime(state)})

    def test_write_file_requires_tool_call_id(self) -> None:
        middleware = FilesystemMiddleware(long_term_memory=False)
        write_tool = next(tool for tool in middleware.tools if tool.name == "write_file")
        _ensure_tool_schema(write_tool)
        state = _make_state()
        with pytest.raises(ValueError):
            write_tool.invoke(
                {
                    "file_path": "/notes.txt",
                    "content": "Missing call id",
                    "runtime": _make_runtime(state, tool_call_id=None),
                }
            )

    def test_read_file_missing_local_file_returns_error(self) -> None:
        middleware = FilesystemMiddleware(long_term_memory=False)
        read_tool = next(tool for tool in middleware.tools if tool.name == "read_file")
        _ensure_tool_schema(read_tool)
        state = _make_state()
        result = read_tool.invoke({"file_path": "/unknown.txt", "runtime": _make_runtime(state)})
        assert result == "File '/unknown.txt' not found"

    def test_write_file_blocks_overwrite(self) -> None:
        middleware = FilesystemMiddleware(long_term_memory=False)
        write_tool = next(tool for tool in middleware.tools if tool.name == "write_file")
        _ensure_tool_schema(write_tool)
        state = _make_state(files={"/notes.txt": _file_data("Keep me")})
        runtime = _make_runtime(state, tool_call_id="write-dup")
        error = write_tool.invoke({"file_path": "/notes.txt", "content": "New", "runtime": runtime})
        assert isinstance(error, str)
        assert "already exists" in error


@pytest.mark.requires("langchain_openai")
class TestSubagentMiddleware:
    """Test the SubagentMiddleware class."""

    def test_subagent_middleware_init(self):
        middleware = SubAgentMiddleware(
            default_model="gpt-4o-mini",
        )
        assert middleware is not None
        assert middleware.system_prompt is TASK_SYSTEM_PROMPT
        assert len(middleware.tools) == 1
        assert middleware.tools[0].name == "task"
        expected_desc = TASK_TOOL_DESCRIPTION.format(available_agents=f"- general-purpose: {DEFAULT_GENERAL_PURPOSE_DESCRIPTION}")
        assert middleware.tools[0].description == expected_desc

    def test_default_subagent_with_tools(self):
        middleware = SubAgentMiddleware(
            default_model="gpt-4o-mini",
            default_tools=[],
        )
        assert middleware is not None
        assert middleware.system_prompt == TASK_SYSTEM_PROMPT

    def test_default_subagent_custom_system_prompt(self):
        middleware = SubAgentMiddleware(
            default_model="gpt-4o-mini",
            default_tools=[],
            system_prompt="Use the task tool to call a subagent.",
        )
        assert middleware is not None
        assert middleware.system_prompt == "Use the task tool to call a subagent."


class TestPatchToolCallsMiddleware:
    def test_first_message(self) -> None:
        input_messages = [
            SystemMessage(content="You are a helpful assistant.", id="1"),
            HumanMessage(content="Hello, how are you?", id="2"),
        ]
        middleware = PatchToolCallsMiddleware()
        state_update = middleware.before_agent({"messages": input_messages}, None)
        assert state_update is not None
        assert len(state_update["messages"]) == 3
        assert state_update["messages"][0].type == "remove"
        assert state_update["messages"][1].type == "system"
        assert state_update["messages"][1].content == "You are a helpful assistant."
        assert state_update["messages"][2].type == "human"
        assert state_update["messages"][2].content == "Hello, how are you?"
        assert state_update["messages"][2].id == "2"

    def test_missing_tool_call(self) -> None:
        input_messages = [
            SystemMessage(content="You are a helpful assistant.", id="1"),
            HumanMessage(content="Hello, how are you?", id="2"),
            AIMessage(
                content="I'm doing well, thank you!",
                tool_calls=[ToolCall(id="123", name="get_events_for_days", args={"date_str": "2025-01-01"})],
                id="3",
            ),
            HumanMessage(content="What is the weather in Tokyo?", id="4"),
        ]
        middleware = PatchToolCallsMiddleware()
        state_update = middleware.before_agent({"messages": input_messages}, None)
        assert state_update is not None
        assert len(state_update["messages"]) == 6
        assert state_update["messages"][0].type == "remove"
        assert state_update["messages"][1] == input_messages[0]
        assert state_update["messages"][2] == input_messages[1]
        assert state_update["messages"][3] == input_messages[2]
        assert state_update["messages"][4].type == "tool"
        assert state_update["messages"][4].tool_call_id == "123"
        assert state_update["messages"][4].name == "get_events_for_days"
        assert state_update["messages"][5] == input_messages[3]
        updated_messages = add_messages(input_messages, state_update["messages"])
        assert len(updated_messages) == 5
        assert updated_messages[0] == input_messages[0]
        assert updated_messages[1] == input_messages[1]
        assert updated_messages[2] == input_messages[2]
        assert updated_messages[3].type == "tool"
        assert updated_messages[3].tool_call_id == "123"
        assert updated_messages[3].name == "get_events_for_days"
        assert updated_messages[4] == input_messages[3]

    def test_no_missing_tool_calls(self) -> None:
        input_messages = [
            SystemMessage(content="You are a helpful assistant.", id="1"),
            HumanMessage(content="Hello, how are you?", id="2"),
            AIMessage(
                content="I'm doing well, thank you!",
                tool_calls=[ToolCall(id="123", name="get_events_for_days", args={"date_str": "2025-01-01"})],
                id="3",
            ),
            ToolMessage(content="I have no events for that date.", tool_call_id="123", id="4"),
            HumanMessage(content="What is the weather in Tokyo?", id="5"),
        ]
        middleware = PatchToolCallsMiddleware()
        state_update = middleware.before_agent({"messages": input_messages}, None)
        assert state_update is not None
        assert len(state_update["messages"]) == 6
        assert state_update["messages"][0].type == "remove"
        assert state_update["messages"][1:] == input_messages
        updated_messages = add_messages(input_messages, state_update["messages"])
        assert len(updated_messages) == 5
        assert updated_messages == input_messages

    def test_two_missing_tool_calls(self) -> None:
        input_messages = [
            SystemMessage(content="You are a helpful assistant.", id="1"),
            HumanMessage(content="Hello, how are you?", id="2"),
            AIMessage(
                content="I'm doing well, thank you!",
                tool_calls=[ToolCall(id="123", name="get_events_for_days", args={"date_str": "2025-01-01"})],
                id="3",
            ),
            HumanMessage(content="What is the weather in Tokyo?", id="4"),
            AIMessage(
                content="I'm doing well, thank you!",
                tool_calls=[ToolCall(id="456", name="get_events_for_days", args={"date_str": "2025-01-01"})],
                id="5",
            ),
            HumanMessage(content="What is the weather in Tokyo?", id="6"),
        ]
        middleware = PatchToolCallsMiddleware()
        state_update = middleware.before_agent({"messages": input_messages}, None)
        assert state_update is not None
        assert len(state_update["messages"]) == 9
        assert state_update["messages"][0].type == "remove"
        assert state_update["messages"][1] == input_messages[0]
        assert state_update["messages"][2] == input_messages[1]
        assert state_update["messages"][3] == input_messages[2]
        assert state_update["messages"][4].type == "tool"
        assert state_update["messages"][4].tool_call_id == "123"
        assert state_update["messages"][4].name == "get_events_for_days"
        assert state_update["messages"][5] == input_messages[3]
        assert state_update["messages"][6] == input_messages[4]
        assert state_update["messages"][7].type == "tool"
        assert state_update["messages"][7].tool_call_id == "456"
        assert state_update["messages"][7].name == "get_events_for_days"
        assert state_update["messages"][8] == input_messages[5]
        updated_messages = add_messages(input_messages, state_update["messages"])
        assert len(updated_messages) == 8
        assert updated_messages[0] == input_messages[0]
        assert updated_messages[1] == input_messages[1]
        assert updated_messages[2] == input_messages[2]
        assert updated_messages[3].type == "tool"
        assert updated_messages[3].tool_call_id == "123"
        assert updated_messages[3].name == "get_events_for_days"
        assert updated_messages[4] == input_messages[3]
        assert updated_messages[5] == input_messages[4]
        assert updated_messages[6].type == "tool"
        assert updated_messages[6].tool_call_id == "456"
        assert updated_messages[6].name == "get_events_for_days"
        assert updated_messages[7] == input_messages[5]


class TestResearchTimerMiddleware:
    def test_timer_sends_warning_message(self, monkeypatch):
        middleware = ResearchTimerMiddleware(total_seconds=120, warning_ratio=0.5)
        state = {"messages": [HumanMessage(content="Start")]}
        runtime = Runtime()

        monkeypatch.setattr("src.agents.deep_agents.middleware.timer.time.monotonic", lambda: 0.0)
        assert middleware.before_model(state, runtime) is None

        monkeypatch.setattr("src.agents.deep_agents.middleware.timer.time.monotonic", lambda: 70.0)
        update = middleware.before_model(state, runtime)
        assert update is not None
        assert isinstance(update["messages"][-1], HumanMessage)
        assert "Time check" in update["messages"][-1].content

    def test_timer_emits_final_message_once(self, monkeypatch):
        middleware = ResearchTimerMiddleware(total_seconds=60, warning_ratio=0.9)
        state = {"messages": [HumanMessage(content="Start")]}
        runtime = Runtime()

        times = iter([0.0, 65.0, 70.0])
        monkeypatch.setattr("src.agents.deep_agents.middleware.timer.time.monotonic", lambda: next(times))

        assert middleware.before_model(state, runtime) is None
        update = middleware.before_model(state, runtime)
        assert update is not None
        final_message = update["messages"][-1]
        assert isinstance(final_message, HumanMessage)
        assert "final summary" in final_message.content.lower()

        # Subsequent call should not duplicate the final message
        second_update = middleware.before_model(state, runtime)
        assert second_update is None
