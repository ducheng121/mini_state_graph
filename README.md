# mini_state_graph

一个用于理解 LangGraph 核心设计的顺序执行 mini 版。

它保留了 LangGraph 最重要的抽象：

- 顺序节点执行
- 条件跳转
- 节点返回 partial update
- 按字段 reducer 合并 state
- execution trace
- checkpoint / `thread_id` / `resume`

它不追求兼容 LangGraph，也不试图覆盖完整 agent runtime。

更准确的定位是：

> LangGraph core ideas, sequential edition

## 当前能力

基础能力：

- `StateGraph`
- `StateSpec`
- `node(state) -> update`
- 固定边与条件边
- reducer 驱动的 state merge
- `ExecutionResult` 和 `StepTrace`

第二阶段增强：

- `StateSpec` 支持字段声明和 `TypedDict`
- 编译期 graph 校验
- 自定义错误类型
- 更完整的 trace 调试信息

第三阶段持久化：

- `InMemoryCheckpointStore`
- `thread_id` 维度的 checkpoint 记录
- `resume(thread_id)` 从最新 checkpoint 恢复
- 指定 `checkpoint_id` 做简单 time travel

## 适用范围

适合：

- 理解 LangGraph 的 state 模型
- 理解 node / update / reducer / routing 的执行链
- 做顺序版 graph demo
- 接入 LLM 或 tool 做串行编排
- 理解 checkpoint / thread / resume 为什么存在

不适合：

- 完整 agent runtime
- 并发 fanout / super-step
- `Send` / `Command`
- 子图调度
- 复杂 interrupt / human-in-the-loop
- LangGraph API 兼容替代

## 安装

开发模式安装：

```bash
pip install -e .
```

不安装也可以直接运行：

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_*.py'
```

## 目录

```text
mini_state_graph/
├── .gitignore
├── pyproject.toml
├── README.md
├── MINIGRAPH_VS_LANGGRAPH.md
├── examples/
│   └── retrieve_grade_answer_demo.py
├── src/mini_state_graph/
│   ├── __init__.py
│   ├── checkpoint.py
│   ├── errors.py
│   ├── executor.py
│   ├── graph.py
│   ├── reducers.py
│   └── state.py
└── tests/
    └── test_mini_graph.py
```

## 运行测试

```bash
python -m unittest discover -s tests -p 'test_*.py'
```

如果你没有执行 `pip install -e .`，那就使用：

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_*.py'
```

## 概念对照

如果你关心“当前这个 mini 版到底和 LangGraph 哪些地方像、哪些地方不像”，看这里：

- [MINIGRAPH_VS_LANGGRAPH.md](./MINIGRAPH_VS_LANGGRAPH.md)

## Checkpoint 示例

```python
from mini_state_graph import END, START, InMemoryCheckpointStore, StateGraph

store = InMemoryCheckpointStore()
graph = StateGraph()

def step_one(state):
    return {"count": state.get("count", 0) + 1}

def step_two(state):
    return {"count": state["count"] + 1}

graph.add_node("step_one", step_one)
graph.add_node("step_two", step_two)
graph.add_edge(START, "step_one")
graph.add_edge("step_one", "step_two")
graph.add_edge("step_two", END)

app = graph.compile(checkpoint_store=store)
paused = app.invoke({"count": 0}, thread_id="demo-thread", stop_after_steps=1)
resumed = app.resume("demo-thread")
print(paused.status, resumed.final_state)
```

## 完整 Demo

提供了一个更接近 LangGraph 学习场景的完整示例：

- `retrieve -> grade -> answer/fallback`
- 展示 reducer 合并
- 展示条件路由
- 展示 `thread_id + checkpoint + resume`
- 打印完整 trace

运行方式：

```bash
PYTHONPATH=src python examples/retrieve_grade_answer_demo.py
```

## 顺序版 LLM / Tool 用法

这个项目可以按“LangGraph 的顺序版”来使用。

例如：

- `retrieve -> grade -> answer`
- `plan -> call_tool -> summarize`
- `classify -> branch -> produce result`

一个典型的 LLM 节点会长这样：

```python
def call_llm(state):
    response = llm.invoke(state["messages"])
    return {"messages": [response]}
```

一个典型的 tool 节点会长这样：

```python
def run_tool(state):
    result = search_tool.invoke(state["query"])
    return {"tool_result": result, "logs": ["tool finished"]}
```

如果要不要走 tool 由 state 决定，可以用条件路由：

```python
def route_after_plan(state):
    return "tool_node" if state["need_tool"] else "answer_node"
```

这已经足够支持很多顺序版 agent / workflow 实验。

## 最小示例

```python
from mini_state_graph import END, START, StateGraph, StateSpec, append_list

spec = StateSpec(reducers={"logs": append_list})
graph = StateGraph(spec)

def retrieve(state):
    return {"docs": ["doc-a"], "logs": ["retrieved"]}

def answer(state):
    return {"answer": f"found {len(state['docs'])} docs", "logs": ["answered"]}

graph.add_node("retrieve", retrieve)
graph.add_node("answer", answer)
graph.add_edge(START, "retrieve")
graph.add_edge("retrieve", "answer")
graph.add_edge("answer", END)

result = graph.compile().invoke({})
print(result.final_state)
print(result.trace)
```

## 和 LangGraph 的区别

这个项目和 LangGraph 的关系，最准确的说法不是“简化版兼容实现”，而是：

> 一个用来帮助理解 LangGraph 核心抽象的顺序执行模型

主要区别：

- 这里只有顺序执行，没有 LangGraph 的 super-step / 并发 fanout
- 这里只有最小 checkpoint 结构，没有完整 persistence runtime 元数据
- 这里只有暂停恢复，没有完整 interrupt 语义
- 这里没有 `Send`、`Command`、子图和更复杂的运行时控制能力
- 这里适合串行 LLM / tool 编排，不适合完整 agent runtime

如果你是为了学 LangGraph，这些差异是有意保留的，因为它们把复杂度压在最关键的抽象之外。

## License

MIT. See [LICENSE](./LICENSE).

## English Summary

`mini_state_graph` is a small educational project for understanding the core ideas behind LangGraph through a sequential runtime.

It keeps the most important concepts:

- graph definition with nodes and edges
- shared state with per-key reducers
- nodes returning partial updates
- conditional routing
- execution trace
- checkpoint, `thread_id`, and resume

It is intentionally not a full LangGraph reimplementation.

This project is good for:

- learning how LangGraph-style state works
- experimenting with sequential LLM or tool workflows
- understanding why checkpointing and resume matter

This project is not meant for:

- concurrent super-step execution
- full agent runtime behavior
- `Send`, `Command`, subgraphs, or advanced interrupts
- API compatibility with LangGraph
