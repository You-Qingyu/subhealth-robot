# Sensor 接口

## 动机

统一传感器描述、最新值和订阅方式，使采集实现可以替换，同时不把传感器协议暴露给任务编排。

## Provider 接口

`SensorProvider` 提供：

- `descriptors`
- `latest`
- `subscribe`

## Registry 接口

`SensorRegistry` 提供：

- `register`
- `descriptors`
- `latest`
- `subscribe`

## 语义

- Provider 负责采集、缓存、查询和发布。
- Sensor 不负责任务决策或动作执行。
- Registry 聚合 provider 的描述和查询；订阅按 filter 中的 sensor ID 选择 provider。
- `SensorSample` 是核心模型；ROS `PhysioSample` 只是 transport 类型，不能直接替代它。

实现见 `ros2_ws/src/services/platform/src/sensor.rs` 和 `services/sensor/src/lib.rs`。
