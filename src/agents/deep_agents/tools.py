import os
from pathlib import Path
from typing import Annotated, Union

from langchain_core.messages import ToolMessage
from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command

from src.agents.agents.tools import InjectedState
from src.agents.deep_agents.prompts import (
    EDIT_FILE_TOOL_DESCRIPTION,
    LIST_FILES_TOOL_DESCRIPTION,
    READ_FILE_TOOL_DESCRIPTION,
    WRITE_FILE_TOOL_DESCRIPTION,
    WRITE_TODOS_TOOL_DESCRIPTION,
)
from src.agents.deep_agents.state import FilesystemState, Todo

_DEFAULT_WORKDIR = Path(os.getenv("DEEP_AGENT_WORKDIR", Path.cwd())).resolve()


def _resolve_path(file_path: str) -> tuple[Path | None, str | None, str | None]:
    """Resolve an incoming path to a workspace-relative absolute path and key.

    Returns (resolved_path, state_key, error_message). The state_key is normalized
    to posix-style relative paths for stable dictionary lookups.
    """
    try:
        path = Path(file_path)
    except (TypeError, ValueError):
        return None, None, f"Error: Invalid path '{file_path}'"

    if not path.is_absolute():
        path = _DEFAULT_WORKDIR / path

    try:
        resolved = path.resolve()
    except OSError:
        return None, None, f"Error: Unable to resolve path '{file_path}'"

    try:
        relative = resolved.relative_to(_DEFAULT_WORKDIR)
    except ValueError:
        return None, None, "Error: Access outside of the workspace is not permitted"

    key = relative.as_posix()
    return resolved, key, None


def _ensure_parent_dir(path: Path) -> str | None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return f"Error: Unable to create directory '{path.parent}': {exc}"
    return None


def _load_from_disk(path: Path) -> tuple[str | None, str | None]:
    try:
        content = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, f"Error: File '{path}' not found"
    except UnicodeDecodeError:
        return None, (
            f"Error: Could not read '{path}' using UTF-8 encoding. "
            "Binary files are not supported."
        )
    except OSError as exc:
        return None, f"Error: Unable to read '{path}': {exc}"
    return content, None


@tool(description=WRITE_TODOS_TOOL_DESCRIPTION)
def write_todos(
    todos: list[Todo], tool_call_id: Annotated[str, InjectedToolCallId]
) -> Command:
    return Command(
        update={
            "todos": todos,
            "messages": [
                ToolMessage(f"Updated todo list to {todos}", tool_call_id=tool_call_id)
            ],
        }
    )


@tool(description=LIST_FILES_TOOL_DESCRIPTION)
def ls(state: Annotated[FilesystemState, InjectedState]) -> list[str]:
    """List all files"""
    files = state.get("files", {}) or {}
    return sorted(files.keys())


@tool(description=READ_FILE_TOOL_DESCRIPTION)
def read_file(
    file_path: str,
    state: Annotated[FilesystemState, InjectedState],
    offset: int = 0,
    limit: int = 2000,
) -> str:
    resolved, key, error = _resolve_path(file_path)
    if error:
        return error

    mock_filesystem = state.get("files", {}) or {}

    if key not in mock_filesystem:
        content, load_error = _load_from_disk(resolved)  # type: ignore[arg-type]
        if load_error:
            return load_error
        # Cache content in state for subsequent operations
        mock_filesystem[key] = content  # type: ignore[assignment]
        state["files"] = mock_filesystem  # type: ignore[index]

    content = mock_filesystem[key]

    # Get file content
    if not isinstance(content, str):
        return f"Error: Stored contents for '{file_path}' are not text."

    # Handle empty file
    if not content or content.strip() == "":
        return "System reminder: File exists but has empty contents"

    # Split content into lines
    lines = content.splitlines()

    # Apply line offset and limit
    start_idx = offset
    end_idx = min(start_idx + limit, len(lines))

    # Handle case where offset is beyond file length
    if start_idx >= len(lines):
        return f"Error: Line offset {offset} exceeds file length ({len(lines)} lines)"

    # Format output with line numbers (cat -n format)
    result_lines = []
    for i in range(start_idx, end_idx):
        line_content = lines[i]

        # Truncate lines longer than 2000 characters
        if len(line_content) > 2000:
            line_content = line_content[:2000]

        # Line numbers start at 1, so add 1 to the index
        line_number = i + 1
        result_lines.append(f"{line_number:6d}\t{line_content}")

    return "\n".join(result_lines)


@tool(description=WRITE_FILE_TOOL_DESCRIPTION)
def write_file(
    file_path: str,
    content: str,
    state: Annotated[FilesystemState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
) -> Command:
    resolved, key, error = _resolve_path(file_path)
    if error:
        return Command(
            update={
                "messages": [
                    ToolMessage(error, tool_call_id=tool_call_id),
                ]
            }
        )

    dir_error = _ensure_parent_dir(resolved)  # type: ignore[arg-type]
    if dir_error:
        return Command(
            update={
                "messages": [
                    ToolMessage(dir_error, tool_call_id=tool_call_id),
                ]
            }
        )

    try:
        resolved.write_text(content, encoding="utf-8")  # type: ignore[arg-type]
    except OSError as exc:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        f"Error: Unable to write file '{resolved}': {exc}",
                        tool_call_id=tool_call_id,
                    )
                ]
            }
        )

    files = state.get("files", {}) or {}
    files[key] = content
    return Command(
        update={
            "files": files,
            "messages": [
                ToolMessage(
                    f"Updated file {resolved}", tool_call_id=tool_call_id  # type: ignore[arg-type]
                )
            ],
        }
    )


@tool(description=EDIT_FILE_TOOL_DESCRIPTION)
def edit_file(
    file_path: str,
    old_string: str,
    new_string: str,
    state: Annotated[FilesystemState, InjectedState],
    tool_call_id: Annotated[str, InjectedToolCallId],
    replace_all: bool = False,
) -> Union[Command, str]:
    """Write to a file."""
    resolved, key, error = _resolve_path(file_path)
    if error:
        return error

    mock_filesystem = state.get("files", {}) or {}
    # Check if file exists in mock filesystem
    if key not in mock_filesystem:
        content, load_error = _load_from_disk(resolved)  # type: ignore[arg-type]
        if load_error:
            return load_error
        mock_filesystem[key] = content

    # Get current file content
    content = mock_filesystem[key]
    if not isinstance(content, str):
        return f"Error: Stored contents for '{file_path}' are not text."

    # Check if old_string exists in the file
    if old_string not in content:
        return f"Error: String not found in file: '{old_string}'"

    # If not replace_all, check for uniqueness
    if not replace_all:
        occurrences = content.count(old_string)
        if occurrences > 1:
            return f"Error: String '{old_string}' appears {occurrences} times in file. Use replace_all=True to replace all instances, or provide a more specific string with surrounding context."
        elif occurrences == 0:
            return f"Error: String not found in file: '{old_string}'"

    # Perform the replacement
    if replace_all:
        new_content = content.replace(old_string, new_string)
        replacement_count = content.count(old_string)
        result_msg = f"Successfully replaced {replacement_count} instance(s) of the string in '{file_path}'"
    else:
        new_content = content.replace(
            old_string, new_string, 1
        )  # Replace only first occurrence
        result_msg = f"Successfully replaced string in '{file_path}'"

    # Update the mock filesystem
    mock_filesystem[key] = new_content

    dir_error = _ensure_parent_dir(resolved)  # type: ignore[arg-type]
    if dir_error:
        return dir_error

    try:
        resolved.write_text(new_content, encoding="utf-8")  # type: ignore[arg-type]
    except OSError as exc:
        return f"Error: Unable to write updates to '{resolved}': {exc}"

    return Command(
        update={
            "files": mock_filesystem,
            "messages": [ToolMessage(result_msg, tool_call_id=tool_call_id)],
        }
    )
