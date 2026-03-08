from __future__ import annotations

from pprint import pprint

from mini_state_graph import (
    END,
    START,
    InMemoryCheckpointStore,
    StateField,
    StateGraph,
    StateSpec,
    append_list,
)


def build_demo_app():
    spec = StateSpec.from_field_defs(
        [
            StateField(name="question"),
            StateField(name="documents"),
            StateField(name="decision"),
            StateField(name="answer"),
            StateField(name="logs", reducer=append_list),
        ]
    )

    graph = StateGraph(spec)

    def retrieve(state):
        question = state["question"]
        docs = ["langgraph-overview", "state-management-notes"]
        return {
            "documents": docs,
            "logs": [f"retrieved {len(docs)} docs for '{question}'"],
        }

    def grade(state):
        has_docs = bool(state.get("documents"))
        decision = "answer" if has_docs else "fallback"
        return {
            "decision": decision,
            "logs": [f"graded retrieval -> {decision}"],
        }

    def route_after_grade(state):
        return state["decision"]

    def answer(state):
        return {
            "answer": f"Answer based on {len(state['documents'])} docs for: {state['question']}",
            "logs": ["generated answer"],
        }

    def fallback(state):
        return {
            "answer": "No relevant documents found.",
            "logs": ["used fallback answer"],
        }

    graph.add_node("retrieve", retrieve)
    graph.add_node("grade", grade)
    graph.add_node("answer", answer)
    graph.add_node("fallback", fallback)

    graph.add_edge(START, "retrieve")
    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges("grade", route_after_grade)
    graph.add_edge("answer", END)
    graph.add_edge("fallback", END)

    store = InMemoryCheckpointStore()
    return graph.compile(checkpoint_store=store), store


def print_trace(result):
    print("\nTRACE")
    for step in result.trace:
        print(f"- step={step.step} node={step.node} next={step.next_node}")
        print("  input_state:")
        pprint(step.input_state, indent=4)
        print("  update:")
        pprint(step.update, indent=4)
        print("  state_snapshot:")
        pprint(step.state_snapshot, indent=4)


def main() -> None:
    app, store = build_demo_app()

    print("=== Run once, then pause after 2 steps ===")
    paused = app.invoke(
        {"question": "What is LangGraph state?"},
        thread_id="demo-thread",
        stop_after_steps=2,
    )
    print(f"status={paused.status} thread_id={paused.thread_id}")
    pprint(paused.final_state)
    print_trace(paused)

    print("\n=== Resume from latest checkpoint ===")
    resumed = app.resume("demo-thread")
    print(f"status={resumed.status} thread_id={resumed.thread_id}")
    pprint(resumed.final_state)
    print_trace(resumed)

    print("\n=== Checkpoint history ===")
    history = app.get_state_history("demo-thread")
    for checkpoint in history:
        print(
            f"- checkpoint_id={checkpoint.checkpoint_id} "
            f"step={checkpoint.step} node={checkpoint.node} next={checkpoint.next_node}"
        )

    print("\n=== Latest checkpoint state ===")
    pprint(store.get_latest("demo-thread").state if store.get_latest("demo-thread") else None)


if __name__ == "__main__":
    main()
