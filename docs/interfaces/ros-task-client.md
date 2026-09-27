# ROS Task Client 接口

## 动机

把 canonical `Task` 与 ROS `ExecuteTask` action 之间的映射、设备注册表、ROS executor 生命周期集中在一个控制平面模块中。

## 公开函数

`RosTaskClient`：

- `init`
- `init_with_config`
- `validate`
- `execute`

`RosTaskRuntime` 负责 ROS executor 的运行与关闭。

## 配置

配置通过 `ROS_TASK_CLIENT_CONFIG` 指定 YAML 文件。当前配置包含：

- `version`，必须为 `1`；
- ROS node 名称、feedback buffer 和 server wait timeout；
- enabled device 的 `id` 与绝对 ROS `action_name`。

## 语义

- 未注册或 disabled 的设备不能执行任务。
- device ID 和 action name 必须唯一。
- ROS action 类型只在 client 和 mapper 内部使用，不能进入 service 核心。
- action server 不可用、goal 被拒绝、feedback 溢出和 shutdown 都会返回执行错误。

实现见 `ros2_ws/src/control_plane/ros_task_client`。
