# 模块接口

这些文档描述当前代码中真实存在的模块接口，而不是未来架构或完整数据模型。

| 模块 | 接口文档 | 主要 seam |
|---|---|---|
| Platform | [platform](platform.md) | canonical 类型、执行会话和状态事件 |
| Repository | [repository](repository.md) | 任务状态的唯一真相源 |
| Orchestration | [orchestration](orchestration.md) | 任务提交、反馈和终态应用 |
| Execution | [execution](execution.md) | `ExecutionPort` 与具体执行实现 |
| Gateway | [gateway](gateway.md) | HTTP/WS 到控制平面的入口 |
| ROS task client | [ros-task-client](ros-task-client.md) | canonical task 到 ROS action 的映射 |
| Sensor | [sensor](sensor.md) | SensorProvider 注册、查询和订阅 |

接口卡片不复制代码中的 struct 定义。调用者需要的精确签名、字段和实现细节应直接查看源码。
