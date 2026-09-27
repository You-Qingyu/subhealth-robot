# 文档入口

本文档描述当前代码已经实现的系统。类型、函数签名和 ROS 接口以代码为准；本目录只补充模块动机、协作关系和不能从签名直接看出的语义。

## 当前实现

- [模块接口](interfaces/README.md)：模块之间的 seam、公开入口、错误和生命周期约束。
- [设计决策](decisions/README.md)：当前实现仍然依赖的架构取舍及其动机。
- [Rustdoc 准则](standards/rustdoc.md)：Rust 公开接口注释的语言、格式和内容约定。
- [快速开始](guide/getting-started.md)：构建、运行和开发环境。
- [ROS mock 指南](guide/ros-mocks.md)：mock endpoint 和 ROS 接口的运行方式。
- [TonyPi 真机 endpoint](guide/tonypi-exec.md)：真机 endpoint 的构建、配置和已知限制。
- [医学资料](medical/)：健康诊断相关的领域资料。

## 文档边界

- Rust 类型和函数签名：`ros2_ws/src` 中的 Rust 代码。
- ROS message/action：`ros2_ws/src/interfaces` 中的定义文件。
- ROS endpoint：`ros2_ws/src/mocks` 和 `ros2_ws/src/endpoints` 中的节点代码。
- HTTP 和 WebSocket 路由：`ros2_ws/src/services/gateway` 中的代码。
- 配置格式及校验：`ros2_ws/src/control_plane/ros_task_client/src/config.rs`。

历史 RFC 和未实现的设计不作为当前实现依据；它们仍可通过 Git 历史查阅。
