"""Small demo exercising the FilesystemMiddleware tools without requiring an LLM."""
from __future__ import annotations

import pathlib
import sys
from datetime import UTC, datetime
from typing import Any, Dict, List


# Ensure the repository `src/` package resolves even when the script is run from `examples/`.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from langgraph.store.memory import InMemoryStore
from langgraph.types import Command

from src.agents.agents.tools.tool_node import ToolRuntime
from src.agents.deep_agents.middleware.filesystem import FileData, FilesystemMiddleware, FilesystemState


def _iso_now() -> str:
    return datetime.now(UTC).isoformat()


def _make_file_data(content: str) -> FileData:
    lines = content.split("\n")
    timestamp = _iso_now()
    return {
        "content": lines,
        "created_at": timestamp,
        "modified_at": timestamp,
    }


def _make_state(initial_files: Dict[str, FileData] | None = None) -> FilesystemState:
    return FilesystemState(messages=[], files=initial_files or {})


def _make_runtime(
    state: FilesystemState,
    *,
    tool_call_id: str,
    store: InMemoryStore | None = None,
) -> ToolRuntime[None, FilesystemState]:
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
    if not update:
        return
    files_patch: Dict[str, FileData] | None = update.get("files")
    if files_patch:
        files = dict(state.get("files", {}))
        files.update(files_patch)
        state["files"] = files
    message_patch: List[Any] | None = update.get("messages")
    if message_patch:
        existing_messages = list(state.get("messages", []))
        existing_messages.extend(message_patch)
        state["messages"] = existing_messages


def run_short_term_demo() -> None:
    print("-- Short-term Filesystem Demo --")
    state = _make_state({"/readme.txt": _make_file_data("Hello from the short-term store!")})
    middleware = FilesystemMiddleware(long_term_memory=False)
    tools = {tool.name: tool for tool in middleware.tools}

    ls_runtime = _make_runtime(state, tool_call_id="ls-1")
    print("ls =>", tools["ls"].invoke({"runtime": ls_runtime}))

    read_runtime = _make_runtime(state, tool_call_id="read-1")
    print("read_file =>\n", tools["read_file"].invoke({"file_path": "/readme.txt", "runtime": read_runtime}))

    write_runtime = _make_runtime(state, tool_call_id="write-1")
    write_result = tools["write_file"].invoke({
        "file_path": "/notes.txt",
        "content": "Some scratch notes",
        "runtime": write_runtime,
    })
    if isinstance(write_result, Command):
        _apply_command(state, write_result)
        print("write_file => state updated with /notes.txt")
    else:
        print("write_file =>", write_result)

    edit_runtime = _make_runtime(state, tool_call_id="edit-1")
    edit_result = tools["edit_file"].invoke({
        "file_path": "/notes.txt",
        "old_string": "scratch",
        "new_string": "updated scratch",
        "runtime": edit_runtime,
        "replace_all": True,
    })
    if isinstance(edit_result, Command):
        _apply_command(state, edit_result)
        print("edit_file => state updated with edited /notes.txt")
    else:
        print("edit_file =>", edit_result)

    final_read_runtime = _make_runtime(state, tool_call_id="read-2")
    print(
        "read_file (after edit) =>\n",
        tools["read_file"].invoke({"file_path": "/notes.txt", "runtime": final_read_runtime}),
    )
    print()


def run_long_term_demo() -> None:
    print("-- Long-term Filesystem Demo --")
    state = _make_state({"/local.txt": _make_file_data("Short-term entry")})
    store = InMemoryStore()
    store.put(("filesystem",), "/memo.txt", {
        "content": ["Persisted line"],
        "created_at": _iso_now(),
        "modified_at": _iso_now(),
    })

    middleware = FilesystemMiddleware(long_term_memory=True)
    tools = {tool.name: tool for tool in middleware.tools}

    ls_runtime = _make_runtime(state, tool_call_id="ls-long", store=store)
    print("ls =>", tools["ls"].invoke({"runtime": ls_runtime}))

    read_runtime = _make_runtime(state, tool_call_id="read-long", store=store)
    print(
        "read_file(/memories/memo.txt) =>\n",
        tools["read_file"].invoke({
            "file_path": "/memories/memo.txt",
            "runtime": read_runtime,
        }),
    )

    write_runtime = _make_runtime(state, tool_call_id="write-long", store=store)
    write_result = tools["write_file"].invoke({
        "file_path": "/memories/journal.txt",
        "content": "Persist me to long-term memory",
        "runtime": write_runtime,
    })
    print("write_file(/memories/journal.txt) =>", write_result)

    edit_runtime = _make_runtime(state, tool_call_id="edit-long", store=store)
    edit_result = tools["edit_file"].invoke({
        "file_path": "/memories/journal.txt",
        "old_string": "Persist",
        "new_string": "Store",
        "runtime": edit_runtime,
    })
    print("edit_file(/memories/journal.txt) =>", edit_result)

    final_ls_runtime = _make_runtime(state, tool_call_id="ls-long-2", store=store)
    print("ls (after writes) =>", tools["ls"].invoke({"runtime": final_ls_runtime}))
    print()


if __name__ == "__main__":
    run_short_term_demo()
    run_long_term_demo()
