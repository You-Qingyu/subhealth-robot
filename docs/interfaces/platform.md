# Platform 接口

## 动机

为服务之间提供设备无关的 canonical 类型，避免 HTTP、ROS generated type 或具体设备类型进入业务模块。

## 公开内容

`platform` 重新导出：

- `TaskId`、`DeviceId`、`SensorId`
- `DeviceDescriptor`、`DeviceState`
- `Primitive`、`Task`、`TaskRecord`、`TaskState`
- `ExecutionFeedback`、`ExecutionResult`、`ExecutionSession`
- `TaskRepository` 及其错误类型
- `SensorProvider` 及传感器类型
- `SystemEvent`

真实签名见 `ros2_ws/src/services/platform/src/lib.rs` 及其子模块。

## 关键语义

- `Task` 是执行请求；`TaskRecord` 是带状态的持久记录。
- `ExecutionSession` 将反馈流和终态结果绑定到一次执行。
- `SystemEvent` 是状态变化通知，不是任务状态的第二份存储。
- 具体 transport 必须显式映射到这些类型。
