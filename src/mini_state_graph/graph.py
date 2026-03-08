"""Graph definition and compilation."""

from __future__ import annotations

from .checkpoint import CheckpointStore
from .errors import GraphValidationError
from .executor import GraphExecutor, NodeFunc, RouterFunc
from .state import StateSpec

START = "__start__"
END = "__end__"


class StateGraph:
    """Minimal sequential state graph."""

    def __init__(self, spec: StateSpec | None = None) -> None:
        self._spec = spec or StateSpec()
        self._nodes: dict[str, NodeFunc] = {}
        self._edges: dict[str, str] = {}
        self._conditional_edges: dict[str, RouterFunc] = {}

    def add_node(self, name: str, func: NodeFunc) -> None:
        if name in {START, END}:
            raise GraphValidationError(f"'{name}' is reserved")
        if name in self._nodes:
            raise GraphValidationError(f"Node '{name}' is already registered")
        self._nodes[name] = func

    def add_edge(self, source: str, target: str) -> None:
        self._validate_source_name(source)
        self._validate_endpoint(target)
        if source in self._conditional_edges:
            raise GraphValidationError(f"Node '{source}' already has conditional routing")
        self._edges[source] = target

    def add_conditional_edges(self, source: str, router: RouterFunc) -> None:
        self._validate_source_name(source)
        if source in self._edges:
            raise GraphValidationError(f"Node '{source}' already has a fixed edge")
        if source in self._conditional_edges:
            raise GraphValidationError(f"Node '{source}' already has conditional routing")
        self._conditional_edges[source] = router

    def compile(self, *, checkpoint_store: CheckpointStore | None = None) -> GraphExecutor:
        self._validate()
        return GraphExecutor(
            spec=self._spec,
            nodes=dict(self._nodes),
            edges=dict(self._edges),
            conditional_edges=dict(self._conditional_edges),
            start_node=START,
            end_node=END,
            checkpoint_store=checkpoint_store,
        )

    def _validate(self) -> None:
        if START not in self._edges and START not in self._conditional_edges:
            raise GraphValidationError("Graph must define an outgoing edge from START")

        for source, target in self._edges.items():
            if source != START and source not in self._nodes:
                raise GraphValidationError(f"Unknown edge source '{source}'")
            self._validate_endpoint(target)

        for source in self._conditional_edges:
            if source != START and source not in self._nodes:
                raise GraphValidationError(f"Unknown router source '{source}'")

        for node_name in self._nodes:
            if node_name not in self._edges and node_name not in self._conditional_edges:
                raise GraphValidationError(f"Node '{node_name}' has no outgoing edge")

    def _validate_endpoint(self, target: str) -> None:
        if target != END and target not in self._nodes:
            raise GraphValidationError(f"Unknown edge target '{target}'")

    def _validate_source_name(self, source: str) -> None:
        if source != START and source not in self._nodes:
            raise GraphValidationError(f"Unknown edge source '{source}'")
