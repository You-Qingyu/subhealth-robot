# Canonical task 与 transport 映射

## 决策

`platform::Task` 是服务之间的 canonical task。HTTP 请求和 ROS `ExecuteTask` action 都必须显式映射到它们，而不是让 generated transport 类型进入核心服务。

## 动机

HTTP、ROS 发行版和设备 endpoint 的变化不应迫使 Orchestration 或 Repository 改变业务模型。显式 mapper 也让 transport 字段缺失或转换失败的位置清晰可见。

## 当前范围

当前 primitive 只有 `go_to_tag`；ROS action 使用 `task_id`、`device_id`、`primitive`、`payload_json` 和 deadline 字段。未来扩展必须先修改 canonical model，再修改各 transport 映射。
