"""Checkpoint storage for persistence and resume."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .state import State


@dataclass(slots=True)
class Checkpoint:
    thread_id: str
    checkpoint_id: str
    step: int
    node: str
    state: State
    next_node: str
    metadata: dict[str, Any] = field(default_factory=dict)


class CheckpointStore:
    """Abstract checkpoint storage."""

    def save(self, checkpoint: Checkpoint) -> Checkpoint:
        raise NotImplementedError

    def get_latest(self, thread_id: str) -> Checkpoint | None:
        raise NotImplementedError

    def get(self, thread_id: str, checkpoint_id: str) -> Checkpoint | None:
        raise NotImplementedError

    def list(self, thread_id: str) -> list[Checkpoint]:
        raise NotImplementedError


class InMemoryCheckpointStore(CheckpointStore):
    """Simple in-memory checkpoint storage grouped by thread."""

    def __init__(self) -> None:
        self._checkpoints: dict[str, list[Checkpoint]] = {}

    def save(self, checkpoint: Checkpoint) -> Checkpoint:
        bucket = self._checkpoints.setdefault(checkpoint.thread_id, [])
        bucket.append(checkpoint)
        return checkpoint

    def get_latest(self, thread_id: str) -> Checkpoint | None:
        bucket = self._checkpoints.get(thread_id, [])
        return bucket[-1] if bucket else None

    def get(self, thread_id: str, checkpoint_id: str) -> Checkpoint | None:
        for checkpoint in self._checkpoints.get(thread_id, []):
            if checkpoint.checkpoint_id == checkpoint_id:
                return checkpoint
        return None

    def list(self, thread_id: str) -> list[Checkpoint]:
        return list(self._checkpoints.get(thread_id, []))
