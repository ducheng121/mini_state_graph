"""Runtime for executing a compiled state graph."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable
from uuid import uuid4

from .checkpoint import Checkpoint, CheckpointStore
from .errors import ExecutionDebugContext, InvalidUpdateError, NodeExecutionError, RoutingError
from .state import State, StateSpec, Update

NodeFunc = Callable[[State], Update]
RouterFunc = Callable[[State], str]


@dataclass(slots=True)
class StepTrace:
    step: int
    node: str
    input_state: State
    update: Update
    state_snapshot: State
    next_node: str


@dataclass(slots=True)
class ExecutionResult:
    final_state: State
    trace: list[StepTrace] = field(default_factory=list)
    visited_nodes: list[str] = field(default_factory=list)
    status: str = "completed"
    error: str | None = None
    thread_id: str | None = None
    last_checkpoint_id: str | None = None


class GraphExecutor:
    """Executes nodes sequentially until END is reached."""

    def __init__(
        self,
        *,
        spec: StateSpec,
        nodes: dict[str, NodeFunc],
        edges: dict[str, str],
        conditional_edges: dict[str, RouterFunc],
        start_node: str,
        end_node: str,
        checkpoint_store: CheckpointStore | None = None,
    ) -> None:
        self._spec = spec
        self._nodes = nodes
        self._edges = edges
        self._conditional_edges = conditional_edges
        self._start_node = start_node
        self._end_node = end_node
        self._checkpoint_store = checkpoint_store

    def invoke(
        self,
        initial_state: State | None = None,
        *,
        max_steps: int = 100,
        thread_id: str | None = None,
        stop_after_steps: int | None = None,
    ) -> ExecutionResult:
        current_node = self._resolve_next(self._start_node, dict(initial_state or {}))
        return self._run(
            state=dict(initial_state or {}),
            current_node=current_node,
            start_step=0,
            max_steps=max_steps,
            thread_id=thread_id,
            stop_after_steps=stop_after_steps,
        )

    def resume(
        self,
        thread_id: str,
        *,
        checkpoint_id: str | None = None,
        max_steps: int = 100,
        stop_after_steps: int | None = None,
    ) -> ExecutionResult:
        if self._checkpoint_store is None:
            raise ValueError("resume() requires a checkpoint store")

        checkpoint = (
            self._checkpoint_store.get(thread_id, checkpoint_id)
            if checkpoint_id is not None
            else self._checkpoint_store.get_latest(thread_id)
        )
        if checkpoint is None:
            raise ValueError(f"No checkpoint found for thread_id='{thread_id}'")

        if checkpoint.next_node == self._end_node:
            return ExecutionResult(
                final_state=dict(checkpoint.state),
                status="completed",
                thread_id=thread_id,
                last_checkpoint_id=checkpoint.checkpoint_id,
            )

        return self._run(
            state=dict(checkpoint.state),
            current_node=checkpoint.next_node,
            start_step=checkpoint.step + 1,
            max_steps=max_steps,
            thread_id=thread_id,
            stop_after_steps=stop_after_steps,
        )

    def get_state_history(self, thread_id: str) -> list[Checkpoint]:
        if self._checkpoint_store is None:
            raise ValueError("get_state_history() requires a checkpoint store")
        return self._checkpoint_store.list(thread_id)

    def _run(
        self,
        *,
        state: State,
        current_node: str,
        start_step: int,
        max_steps: int,
        thread_id: str | None,
        stop_after_steps: int | None,
    ) -> ExecutionResult:
        state = dict(state)
        trace: list[StepTrace] = []
        visited_nodes: list[str] = []
        last_checkpoint_id: str | None = None
        step = start_step

        while current_node != self._end_node:
            if step - start_step >= max_steps:
                raise RuntimeError(f"Graph exceeded max_steps={max_steps}")

            input_state = dict(state)
            debug_context = ExecutionDebugContext(step=step, node=current_node, input_state=input_state)
            node_fn = self._nodes[current_node]

            try:
                update = node_fn(dict(state))
            except Exception as exc:
                raise NodeExecutionError(
                    f"Node '{current_node}' failed at step {step}",
                    context=debug_context,
                    cause=exc,
                ) from exc

            if not isinstance(update, dict):
                raise InvalidUpdateError(
                    f"Node '{current_node}' must return dict, got {type(update).__name__}"
                )

            debug_context.update = dict(update)
            state = self._spec.merge(state, update)

            try:
                next_node = self._resolve_next(current_node, state)
            except KeyError as exc:
                raise RoutingError(
                    f"Routing failed after node '{current_node}' at step {step}: {exc}",
                    context=debug_context,
                ) from exc

            trace.append(
                StepTrace(
                    step=step,
                    node=current_node,
                    input_state=input_state,
                    update=dict(update),
                    state_snapshot=dict(state),
                    next_node=next_node,
                )
            )
            visited_nodes.append(current_node)
            last_checkpoint_id = self._save_checkpoint(
                thread_id=thread_id,
                step=step,
                node=current_node,
                state=state,
                next_node=next_node,
            )
            current_node = next_node
            step += 1

            if stop_after_steps is not None and len(trace) >= stop_after_steps:
                return ExecutionResult(
                    final_state=state,
                    trace=trace,
                    visited_nodes=visited_nodes,
                    status="paused",
                    thread_id=thread_id,
                    last_checkpoint_id=last_checkpoint_id,
                )

        return ExecutionResult(
            final_state=state,
            trace=trace,
            visited_nodes=visited_nodes,
            status="completed",
            thread_id=thread_id,
            last_checkpoint_id=last_checkpoint_id,
        )

    def _save_checkpoint(
        self,
        *,
        thread_id: str | None,
        step: int,
        node: str,
        state: State,
        next_node: str,
    ) -> str | None:
        if self._checkpoint_store is None or thread_id is None:
            return None

        checkpoint = Checkpoint(
            thread_id=thread_id,
            checkpoint_id=str(uuid4()),
            step=step,
            node=node,
            state=dict(state),
            next_node=next_node,
            metadata={"status": "completed" if next_node == self._end_node else "running"},
        )
        self._checkpoint_store.save(checkpoint)
        return checkpoint.checkpoint_id

    def _resolve_next(self, current_node: str, state: State) -> str:
        if current_node in self._conditional_edges:
            next_node = self._conditional_edges[current_node](dict(state))
        else:
            try:
                next_node = self._edges[current_node]
            except KeyError as exc:
                raise KeyError(f"No outgoing edge defined for node '{current_node}'") from exc

        if next_node != self._end_node and next_node not in self._nodes:
            raise KeyError(f"Unknown next node '{next_node}'")

        return next_node
