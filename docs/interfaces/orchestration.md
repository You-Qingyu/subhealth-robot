# Orchestration 接口

## 动机

把任务接受、执行启动和状态更新集中起来，让 Gateway 不直接协调 Execution，也不直接修改任务状态。

## 依赖

- `ExecutionPort`
- `TaskRepository`
- `MapData`

## 公开函数

`Orchestrator` 提供：

- `new`
- `submit`
- `feedback`
- `complete`
- `resolve_target`
- `shortest_path`

`ExecutionPort` 提供：

- `validate`
- `execute`

## 语义

- `submit` 先按地图为目标序列补全最短路径，再验证执行端、创建任务，最后启动执行。
- 输入目标保持原有顺序；每一对相邻目标之间插入地图路径中的中间节点，连接点不会重复。
- 目标为空、目标不存在或任意相邻目标不可达时，`submit` 直接返回错误，不创建任务。
- 执行启动失败时，Orchestrator 尝试将任务写入 failed 终态。
- feedback 和 result 通过 Repository 应用。
- Orchestrator 持有启动时加载的地图，按节点名称解析目标并提供最小代价路径。
- `shortest_path` 的路径规划错误通过 `OrchestrationError::Pathfinding` 暴露；
  地图目标解析错误通过 `OrchestrationError::Map` 暴露。
- Orchestration 不依赖 ROS generated type、HTTP 类型或具体设备 SDK。

实现见 `ros2_ws/src/services/orchestration/src/lib.rs`。
