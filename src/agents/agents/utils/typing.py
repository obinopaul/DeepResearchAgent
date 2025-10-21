from __future__ import annotations

from typing import Union

from typing_extensions import TypeVar

# from langgraph._internal._typing import StateLike
from src.agents.agents._internal._typing import StateLike

__all__ = (
    "StateT",
    "StateT_co",
    "StateT_contra",
    "InputT",
    "OutputT",
    "ContextT",
)

StateT = TypeVar("StateT", bound=StateLike)
"""Type variable used to represent the state in a graph."""

StateT_co = TypeVar("StateT_co", bound=StateLike, covariant=True)

StateT_contra = TypeVar("StateT_contra", bound=StateLike, contravariant=True)

ContextT = TypeVar("ContextT", bound=Union[StateLike, None])
"""Type variable used to represent graph run scoped context (e.g. `StateLike | None`)."""

ContextT_contra = TypeVar(
    "ContextT_contra", bound=Union[StateLike, None], contravariant=True
)

InputT = TypeVar("InputT", bound=StateLike)
"""Type variable used to represent the input to a state graph."""

OutputT = TypeVar("OutputT", bound=StateLike)
"""Type variable used to represent the output of a state graph."""

NodeInputT = TypeVar("NodeInputT", bound=StateLike)
"""Type variable used to represent the input to a node."""

NodeInputT_contra = TypeVar("NodeInputT_contra", bound=StateLike, contravariant=True)
