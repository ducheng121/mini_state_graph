from __future__ import annotations

import unittest
from typing import TypedDict

from mini_state_graph import (
    Checkpoint,
    END,
    START,
    GraphValidationError,
    InMemoryCheckpointStore,
    NodeExecutionError,
    RoutingError,
    StateField,
    StateGraph,
    StateSpec,
    UnknownStateKeyError,
    add_messages_like,
    append_list,
)
from examples.retrieve_grade_answer_demo import build_demo_app


class QAState(TypedDict):
    score: float
    route: str
    result: str


class MiniGraphTests(unittest.TestCase):
    def test_sequential_graph_merges_updates_and_records_trace(self) -> None:
        spec = StateSpec(reducers={"logs": append_list})
        graph = StateGraph(spec)

        def load_query(state):
            return {"query": state["input"], "logs": ["loaded"]}

        def answer(state):
            return {"answer": f"echo:{state['query']}", "logs": ["answered"]}

        graph.add_node("load_query", load_query)
        graph.add_node("answer", answer)
        graph.add_edge(START, "load_query")
        graph.add_edge("load_query", "answer")
        graph.add_edge("answer", END)

        result = graph.compile().invoke({"input": "hello"})

        self.assertEqual(result.final_state["answer"], "echo:hello")
        self.assertEqual(result.final_state["logs"], ["loaded", "answered"])
        self.assertEqual(result.visited_nodes, ["load_query", "answer"])
        self.assertEqual([step.node for step in result.trace], ["load_query", "answer"])
        self.assertEqual(result.trace[0].input_state, {"input": "hello"})
        self.assertEqual(result.trace[-1].next_node, END)

    def test_conditional_routing_uses_merged_state(self) -> None:
        graph = StateGraph()

        def classify(state):
            return {"route": "fallback" if state["score"] < 0.5 else "answer"}

        def answer(state):
            return {"result": "answer"}

        def fallback(state):
            return {"result": "fallback"}

        def router(state):
            return state["route"]

        graph.add_node("classify", classify)
        graph.add_node("answer", answer)
        graph.add_node("fallback", fallback)
        graph.add_edge(START, "classify")
        graph.add_conditional_edges("classify", router)
        graph.add_edge("answer", END)
        graph.add_edge("fallback", END)

        result = graph.compile().invoke({"score": 0.1})

        self.assertEqual(result.final_state["result"], "fallback")
        self.assertEqual(result.visited_nodes, ["classify", "fallback"])

    def test_node_cannot_mutate_runtime_state_in_place(self) -> None:
        graph = StateGraph()

        def first(state):
            state["count"] = 999
            return {"count": 1}

        graph.add_node("first", first)
        graph.add_edge(START, "first")
        graph.add_edge("first", END)

        result = graph.compile().invoke({"count": 0})

        self.assertEqual(result.final_state["count"], 1)

    def test_unknown_state_key_can_be_rejected(self) -> None:
        spec = StateSpec(allowed_keys={"count"})
        graph = StateGraph(spec)

        def first(state):
            return {"other": 1}

        graph.add_node("first", first)
        graph.add_edge(START, "first")
        graph.add_edge("first", END)

        with self.assertRaises(UnknownStateKeyError):
            graph.compile().invoke({"count": 0})

    def test_state_spec_can_be_built_from_typed_dict(self) -> None:
        spec = StateSpec.from_typed_dict(QAState)
        graph = StateGraph(spec)

        def classify(state):
            return {"route": "answer", "result": "ok"}

        graph.add_node("classify", classify)
        graph.add_edge(START, "classify")
        graph.add_edge("classify", END)

        result = graph.compile().invoke({"score": 0.9})

        self.assertEqual(result.final_state["result"], "ok")

    def test_state_spec_can_be_built_from_internal_field_defs(self) -> None:
        spec = StateSpec.from_field_defs(
            [
                StateField(name="messages", reducer=add_messages_like),
            ]
        )

        merged = spec.merge(
            {"messages": [{"id": "1", "content": "old"}]},
            {"messages": [{"id": "1", "content": "new"}, {"id": "2", "content": "next"}]},
        )

        self.assertEqual(
            merged["messages"],
            [{"id": "1", "content": "new"}, {"id": "2", "content": "next"}],
        )

    def test_compile_rejects_node_without_outgoing_edge(self) -> None:
        graph = StateGraph()

        def lonely(state):
            return {"x": 1}

        graph.add_node("lonely", lonely)
        graph.add_edge(START, "lonely")

        with self.assertRaises(GraphValidationError):
            graph.compile()

    def test_runtime_reports_invalid_router_target(self) -> None:
        graph = StateGraph()

        def classify(state):
            return {"route": "missing"}

        def router(state):
            return state["route"]

        graph.add_node("classify", classify)
        graph.add_edge(START, "classify")
        graph.add_conditional_edges("classify", router)

        with self.assertRaises(RoutingError) as ctx:
            graph.compile().invoke({})

        self.assertIn("classify", str(ctx.exception))
        self.assertEqual(ctx.exception.context.node, "classify")

    def test_runtime_wraps_node_failure_with_debug_context(self) -> None:
        graph = StateGraph()

        def broken(state):
            raise ValueError("boom")

        graph.add_node("broken", broken)
        graph.add_edge(START, "broken")
        graph.add_edge("broken", END)

        with self.assertRaises(NodeExecutionError) as ctx:
            graph.compile().invoke({"count": 1})

        self.assertEqual(ctx.exception.context.node, "broken")
        self.assertEqual(ctx.exception.context.input_state, {"count": 1})

    def test_checkpoints_are_saved_per_step_and_history_is_queryable(self) -> None:
        store = InMemoryCheckpointStore()
        spec = StateSpec(reducers={"logs": append_list})
        graph = StateGraph(spec)

        def load_query(state):
            return {"query": state["input"], "logs": ["loaded"]}

        def answer(state):
            return {"answer": f"echo:{state['query']}", "logs": ["answered"]}

        graph.add_node("load_query", load_query)
        graph.add_node("answer", answer)
        graph.add_edge(START, "load_query")
        graph.add_edge("load_query", "answer")
        graph.add_edge("answer", END)

        app = graph.compile(checkpoint_store=store)
        result = app.invoke({"input": "hello"}, thread_id="thread-1")

        self.assertEqual(result.status, "completed")
        history = app.get_state_history("thread-1")
        self.assertEqual(len(history), 2)
        self.assertIsInstance(history[0], Checkpoint)
        self.assertEqual(history[0].node, "load_query")
        self.assertEqual(history[-1].next_node, END)

    def test_resume_continues_from_latest_checkpoint(self) -> None:
        store = InMemoryCheckpointStore()
        spec = StateSpec(reducers={"logs": append_list})
        graph = StateGraph(spec)

        def load_query(state):
            return {"query": state["input"], "logs": ["loaded"]}

        def answer(state):
            return {"answer": f"echo:{state['query']}", "logs": ["answered"]}

        graph.add_node("load_query", load_query)
        graph.add_node("answer", answer)
        graph.add_edge(START, "load_query")
        graph.add_edge("load_query", "answer")
        graph.add_edge("answer", END)

        app = graph.compile(checkpoint_store=store)
        paused = app.invoke({"input": "hello"}, thread_id="thread-2", stop_after_steps=1)

        self.assertEqual(paused.status, "paused")
        self.assertEqual(paused.final_state["logs"], ["loaded"])

        resumed = app.resume("thread-2")

        self.assertEqual(resumed.status, "completed")
        self.assertEqual(resumed.final_state["answer"], "echo:hello")
        self.assertEqual(resumed.final_state["logs"], ["loaded", "answered"])

    def test_resume_can_start_from_specific_checkpoint_for_time_travel(self) -> None:
        store = InMemoryCheckpointStore()
        graph = StateGraph()

        def one(state):
            return {"count": state.get("count", 0) + 1}

        def two(state):
            return {"count": state["count"] + 1}

        graph.add_node("one", one)
        graph.add_node("two", two)
        graph.add_edge(START, "one")
        graph.add_edge("one", "two")
        graph.add_edge("two", END)

        app = graph.compile(checkpoint_store=store)
        app.invoke({"count": 0}, thread_id="thread-3")
        history = app.get_state_history("thread-3")

        replay = app.resume("thread-3", checkpoint_id=history[0].checkpoint_id)

        self.assertEqual(replay.final_state["count"], 2)

    def test_demo_graph_runs_pause_and_resume_flow(self) -> None:
        app, _store = build_demo_app()

        paused = app.invoke(
            {"question": "What is LangGraph state?"},
            thread_id="demo-thread",
            stop_after_steps=2,
        )
        self.assertEqual(paused.status, "paused")
        self.assertEqual(paused.visited_nodes, ["retrieve", "grade"])
        self.assertEqual(paused.final_state["decision"], "answer")

        resumed = app.resume("demo-thread")
        self.assertEqual(resumed.status, "completed")
        self.assertIn("Answer based on", resumed.final_state["answer"])
        self.assertEqual(
            resumed.final_state["logs"],
            [
                "retrieved 2 docs for 'What is LangGraph state?'",
                "graded retrieval -> answer",
                "generated answer",
            ],
        )


if __name__ == "__main__":
    unittest.main()
