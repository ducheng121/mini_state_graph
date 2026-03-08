"""Custom error types for Mini State Graph."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class MiniGraphError(Exception):
    """Base error for the mini graph runtime."""


class GraphValidationError(MiniGraphError):
    """Raised when a graph definition is invalid before execution."""


class InvalidUpdateError(MiniGraphError):
    """Raised when a node returns an invalid update payload."""


class UnknownStateKeyError(MiniGraphError):
    """Raised when a node tries to update an undeclared state key."""


class ReducerExecutionError(MiniGraphError):
    """Raised when a reducer fails while merging state."""


@dataclass(slots=True)
class ExecutionDebugContext:
    step: int
    node: str
    input_state: dict[str, Any]
    update: dict[str, Any] | None = None


class NodeExecutionError(MiniGraphError):
    """Raised when a node fails during execution."""

    def __init__(self, message: str, *, context: ExecutionDebugContext, cause: Exception) -> None:
        super().__init__(message)
        self.context = context
        self.__cause__ = cause


class RoutingError(MiniGraphError):
    """Raised when routing fails after a node execution."""

    def __init__(self, message: str, *, context: ExecutionDebugContext) -> None:
        super().__init__(message)
        self.context = context
