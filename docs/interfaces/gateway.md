# Gateway 接口

## 动机

提供 WebUI 和外部调用者唯一的 HTTP/WebSocket 入口，同时保持任务状态由 Repository 持有。

## HTTP

- `GET /api/v1/tags`：返回启动时加载的 Tag ID 和地点名称（当前配置为中文），不暴露边与权重；修改地图文件后需重启 Gateway。
- `GET /api/v1/tasks`：列出任务。
- `POST /api/v1/tasks`：提交任务，返回 `202 Accepted` 和 `TaskRecord`。
- `GET /api/v1/tasks/{id}`：读取任务记录。
- `GET /api/v1/sensors`：返回已注册传感器的描述（`id`、`kind`、`unit`）。
- `GET /api/v1/sensors/{id}`：返回单个传感器的描述和最新采样 `sample`；尚无数据时 `sample` 为 `null`，未知 ID 返回 `404`。

提交请求字段为 `device_id`、`primitive`、`target` 和可选的 `deadline_ms`。

## WebSocket

- `GET /api/v1/events`：接收带序号的 `TaskStateChanged` 事件。

事件是瞬时通知；客户端需要通过任务查询获得完整记录。当前没有取消路由、鉴权、分页、ETag 或 trace ID 接口。

## 语义

- Gateway 将输入映射为 canonical `Task`，不自行生成任务状态。
- 提交由 `Orchestrator` 执行。
- 执行会话由后台任务消费，反馈和结果经过 Repository 后再发布事件。
- 传感器查询直接读取 `SensorRegistry` 的内存快照，Gateway 不持有传感器状态。

实现见 `ros2_ws/src/services/gateway/src/lib.rs`、`handlers.rs` 和 `state.rs`。
