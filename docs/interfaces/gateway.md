# Gateway 接口

## 动机

提供 WebUI 和外部调用者唯一的 HTTP/WebSocket 入口，同时保持任务状态由 Repository 持有。

## HTTP

- `GET /api/v1/tasks`：列出任务。
- `POST /api/v1/tasks`：提交任务，返回 `202 Accepted` 和 `TaskRecord`。
- `GET /api/v1/tasks/{id}`：读取任务记录。

提交请求字段为 `device_id`、`primitive`、`target` 和可选的 `deadline_ms`。

## WebSocket

- `GET /api/v1/events`：接收带序号的 `TaskStateChanged` 事件。

事件是瞬时通知；客户端需要通过任务查询获得完整记录。当前没有取消路由、鉴权、分页、ETag 或 trace ID 接口。

## 语义

- Gateway 将输入映射为 canonical `Task`，不自行生成任务状态。
- 提交由 `Orchestrator` 执行。
- 执行会话由后台任务消费，反馈和结果经过 Repository 后再发布事件。

实现见 `ros2_ws/src/services/gateway/src/lib.rs`、`handlers.rs` 和 `state.rs`。
