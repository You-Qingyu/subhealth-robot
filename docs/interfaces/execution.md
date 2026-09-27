# Execution 接口

## 动机

为编排层提供设备无关的执行 seam；具体 ROS client 和设备路由隐藏在执行实现之后。

## 公开接口

`ExecutionPort`：

- `validate(&Task)`：检查任务是否能被当前执行实现接受。
- `execute(Task)`：启动任务并返回 `ExecutionSession`。

具体实现 `services::execution::Execution` 还提供：

- `init`
- `shutdown`

## 语义

- `execute` 返回后，feedback stream 和 result future 共同描述一次执行。
- Gateway 消费 feedback，随后等待 result；执行错误会被转换成 failed 结果。
- 当前接口没有独立的取消操作，也没有第二套 command/payload 业务模型。
- 具体 ROS action 名称由配置解析，不由 Orchestration 决定。

实现见 `ros2_ws/src/services/execution/src/lib.rs` 和 `platform/src/execution.rs`。
