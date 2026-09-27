# TaskRepository 接口

## 动机

集中拥有已接受任务及其状态，避免 Gateway、Orchestration 或事件系统各自维护任务副本。

## 调用者

`Orchestrator` 通过 `Arc<dyn TaskRepository>` 使用它；Gateway 通过应用状态查询它。

## 公开函数

- `create_task`
- `get_task`
- `list_tasks`
- `apply_feedback`
- `apply_result`

精确签名见 `ros2_ws/src/services/platform/src/repository.rs`。

## 语义

- 每个操作从调用者视角是原子的。
- Repository 生成任务 ID并创建初始记录。
- terminal record 保留；只有 non-terminal record 占用设备。
- `apply_feedback` 和 `apply_result` 只能作用于已存在且未终止的任务。
- `BusyDevice`、`UnknownTask`、`TerminalTask` 和 `InvalidTarget` 是业务错误，不应被静默转换为成功。

当前实现是 `task_repository::InMemoryTaskRepository`，并非持久化数据库。
