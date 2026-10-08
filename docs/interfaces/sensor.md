# Sensor 接口

## 动机

统一传感器描述、最新值和订阅方式，使采集实现可以替换，同时不把传感器协议暴露给任务编排。

## Provider 接口

`SensorProvider` 提供：

- `descriptors`
- `latest`
- `subscribe`

当前唯一实现是 `ros_sensor_client::RosSensorProvider`，见"接入"。

## Registry 接口

`SensorRegistry` 提供：

- `register`
- `descriptors`
- `descriptor`
- `latest`
- `subscribe`

## 接入

- 配置：`ROS_SENSOR_CONFIG` 指向的 YAML（默认 `ros2_ws/config/sensors.yaml`），列出传感器的 `id`、`topic`、`kind`、`unit`。
- 采集：`ros2_ws/src/control_plane/ros_sensor_client` 按配置订阅 `PhysioSample` 话题，QoS 对齐 publisher（RELIABLE / KEEP_LAST / depth 10），丢弃 `valid=false` 的样本，其余转换为 `SensorSample` 缓存在内存中。
- 组装：Gateway 组合根（`services/gateway/src/main.rs`）创建 `SensorRegistry` 并注册 provider，随后以只读共享放入 `AppState`。
- 查询：`GET /api/v1/sensors` 调用 `descriptors`，`GET /api/v1/sensors/{id}` 调用 `descriptor` 和 `latest`；MCP 的 `list_sensors` / `read_sensor` 覆盖这两个入口。

## 语义

- Provider 负责采集、缓存、查询和发布。
- Sensor 不负责任务决策或动作执行。
- Registry 聚合 provider 的描述和查询；订阅按 filter 中的 sensor ID 选择 provider。
- `latest` 返回最新一次采样；尚无数据时返回 `None`。
- `subscribe` 当前是空实现：`RosSensorProvider` 不产生采样流，采样流接口保留但没有使用者。
- `SensorSample` 是核心模型；ROS `PhysioSample` 只是 transport 类型，不能直接替代它。

实现见 `ros2_ws/src/services/platform/src/sensor.rs`、`services/sensor/src/lib.rs` 和 `ros2_ws/src/control_plane/ros_sensor_client`。
