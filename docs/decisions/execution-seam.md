# 执行 seam 与设备注册表

## 决策

Orchestration 只依赖 `ExecutionPort`。具体 ROS action client 通过 `RosTaskClient` 和 YAML device registry 解析设备 ID 到 action name 的关系。

## 动机

任务编排不应知道 ROS action 名称、设备类型或厂商 SDK。设备配置变化应局部发生在 endpoint/client 配置中，而不是传播到上层业务模块。

## 当前范围

当前 registry 是静态 YAML 配置，控制平面的 Execution backend 仍然只有
ROS task client。正式设备 endpoint 位于控制平面之外：`tonypi_exec_layer`
运行在 TonyPi 主机上，通过同一个 ROS action contract 调用厂商 SDK；厂商 SDK
不进入 Orchestration、Execution 或 Platform。仓库目前没有通用 endpoint adapter
抽象。
