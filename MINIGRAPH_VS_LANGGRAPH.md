# MiniGraph vs LangGraph

这份文档不是 API 手册，而是概念对照表。

目标是回答 3 个问题：

1. 当前这个 `mini_state_graph` 到底在模仿 LangGraph 的哪些核心设计
2. 哪些地方只是“为了理解而保留的最小实现”
3. 哪些能力是 LangGraph 有、但这个 mini 版故意没做的

## 一句话结论

当前这个 MiniGraph 已经体现了 LangGraph 最核心的 5 个点：

- graph 定义
- state 作为共享状态容器
- node 返回 partial update
- reducer 按字段合并 state
- checkpoint / thread_id / resume 的最小闭环

但它仍然是一个**顺序执行版**。

它更像：

- LangGraph core ideas in miniature

而不是：

- a minimal reimplementation of the full LangGraph runtime

## 核心概念对照

### 1. Graph

LangGraph:

- 用 `StateGraph(...)` 定义图
- 注册节点
- 定义普通边和条件边
- `compile()` 后得到可执行对象

MiniGraph:

- 用 `StateGraph(...)` 定义图
- `add_node()`
- `add_edge()`
- `add_conditional_edges()`
- `compile()` 后得到 `GraphExecutor`

对应关系：

- [`src/mini_state_graph/graph.py`](./src/mini_state_graph/graph.py)

结论：

这一层已经非常像 LangGraph 的心智模型。

### 2. State

LangGraph:

- state 不是普通 dict
- state 是“schema + per-key reducer”
- schema 常见形式是 `TypedDict`

MiniGraph:

- `StateSpec` 表达 state 规则
- 可用 `from_typed_dict()` 从 `TypedDict` 创建
- 可用 `StateField` / `from_field_defs()` 做内部字段声明
- `merge()` 统一负责 update 合并

对应关系：

- [`src/mini_state_graph/state.py`](./src/mini_state_graph/state.py)

结论：

这部分已经抓住了 LangGraph 最核心的 state 设计。

### 3. Node

LangGraph:

- 节点接收当前 state
- 返回部分更新
- 不推荐节点直接修改共享 state

MiniGraph:

- 节点签名是 `node(state) -> dict`
- 执行器给节点传的是 state 副本
- runtime 统一 merge update

对应关系：

- [`src/mini_state_graph/executor.py`](./src/mini_state_graph/executor.py)

结论：

这也是当前 mini 版最重要、最像 LangGraph 的部分之一。

### 4. Reducer

LangGraph:

- 每个 state key 可以声明 reducer
- 没声明时默认覆盖
- `messages` 这种字段会有专门合并语义

MiniGraph:

- `override`
- `append_list`
- `add_messages_like`
- `StateSpec.merge()` 在 runtime 中调用 reducer

对应关系：

- [`src/mini_state_graph/reducers.py`](./src/mini_state_graph/reducers.py)
- [`src/mini_state_graph/state.py`](./src/mini_state_graph/state.py)

结论：

这部分已经足以帮助理解“为什么 LangGraph 的 state 不是普通 dict”。

### 5. Routing

LangGraph:

- 支持固定边
- 支持条件边
- router 根据 state 决定下一跳

MiniGraph:

- `add_edge()`
- `add_conditional_edges()`
- router 签名统一为 `router(state) -> str`

对应关系：

- [`src/mini_state_graph/graph.py`](./src/mini_state_graph/graph.py)
- [`src/mini_state_graph/executor.py`](./src/mini_state_graph/executor.py)

结论：

条件路由的核心思路已经具备。

### 6. Trace / Debug

LangGraph:

- 可以观察图的执行过程
- 持久化和调试都依赖运行轨迹

MiniGraph:

- `StepTrace` 记录：
  - `step`
  - `node`
  - `input_state`
  - `update`
  - `state_snapshot`
  - `next_node`
- `ExecutionResult` 返回完整 trace

对应关系：

- [`src/mini_state_graph/executor.py`](./src/mini_state_graph/executor.py)

结论：

这个实现已经足够支持“手动走读”和调试。

### 7. Checkpoint / Thread / Resume

LangGraph:

- 用 checkpoint 保存执行快照
- 用 `thread_id` 区分会话/运行线
- 支持从 checkpoint 恢复执行

MiniGraph:

- `Checkpoint`
- `CheckpointStore`
- `InMemoryCheckpointStore`
- `invoke(..., thread_id=...)`
- `resume(thread_id, checkpoint_id=None)`
- `get_state_history(thread_id)`

对应关系：

- [`src/mini_state_graph/checkpoint.py`](./src/mini_state_graph/checkpoint.py)
- [`src/mini_state_graph/executor.py`](./src/mini_state_graph/executor.py)

结论：

这部分已经能说明 LangGraph 为什么需要 persistence / thread / resume。

## 当前 MiniGraph 刻意简化了什么

这些简化是有意的，不是缺陷。

### 1. 顺序执行代替 super-step

LangGraph 更接近 Pregel 风格运行时，支持：

- 同一轮多个节点并发执行
- 多个 update 在同一个 step 合并

当前 MiniGraph 只有：

- 单节点顺序执行

影响：

- 你能理解 reducer 的基本意义
- 但还不能真正理解并发 fanout 下的冲突合并语义

### 2. 没有并发冲突模型

LangGraph 会处理一个重要问题：

- 同一步里多个节点同时更新同一个 key 怎么办

当前 MiniGraph 不存在这个问题，因为它一次只跑一个节点。

影响：

- 当前 reducer 更像“字段合并策略”
- 还不像 LangGraph 里那种“并发写入语义定义器”

### 3. checkpoint 只保存最小信息

LangGraph 的 persistence 会带更多运行时信息。

当前 MiniGraph 的 checkpoint 只保留：

- `thread_id`
- `checkpoint_id`
- `step`
- `node`
- `state`
- `next_node`
- `metadata`

影响：

- 已够解释 resume / history / time travel
- 但还不是完整的 runtime persistence

### 4. 没有 interrupt / human-in-the-loop 语义

LangGraph 可以在图运行中断下来，等待外部输入，再继续。

当前 MiniGraph 只有：

- `stop_after_steps`
- `resume()`

这更像“教学用暂停”，不是完整 interrupt 机制。

### 5. 没有 Command / Send / 子图

LangGraph 还有更高级的运行时控制能力：

- `Command`
- `Send`
- subgraph

当前 MiniGraph 没做这些。

原因：

- 它们不是理解 LangGraph 核心 state 模型的第一优先级
- 加进去会显著提高复杂度

## 当前版本最适合用来理解什么

当前 MiniGraph 最适合用来理解：

1. 为什么节点应该返回 update，而不是直接改共享 state
2. 为什么 reducer 要按字段定义
3. graph 是怎么驱动 state 一步步演化的
4. 条件路由为什么是“基于 merge 后的 state”
5. checkpoint / thread_id / resume 为什么属于运行时外层结构，而不是业务 state 本身

## 当前版本不适合拿来理解什么

当前 MiniGraph 不适合拿来推导：

1. LangGraph 的并发执行模型
2. 并发写同一 state key 的冲突语义
3. interrupt / command / send 的完整运行机制
4. LangGraph 全部 API 的兼容细节

## 一个最准确的定位

如果要给当前项目一个最准确的定位，我建议是：

> 一个用于理解 LangGraph 核心设计的顺序执行 mini 版

这个定位是准确的，因为它：

- 保留了最关键的抽象
- 刻意砍掉了高复杂度 runtime 机制
- 足够小，适合手动推演和自己实现一遍

## 推荐使用方式

最适合的使用方式不是把它当库，而是把它当“模型机”：

1. 先画一张小图
2. 写几个节点
3. 手动看每一步 `update -> merge -> next_node`
4. 再看 trace 和 checkpoint
5. 最后再回头看 LangGraph 官方文档

如果你这样用，这个 MiniGraph 已经足够有价值。
