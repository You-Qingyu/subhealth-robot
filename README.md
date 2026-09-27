# ROS Subhealth

设备无关的机器人任务控制系统原型。WebUI 通过 Gateway 提交任务，
Orchestration 管理任务生命周期，Execution 通过 ROS action client 将任务转发到
配置的设备。当前仓库还包含 ROS 2 接口定义和用于开发验证的 mock 节点。

## 架构

```text
WebUI → Gateway → Orchestration → Execution → ROS action server
                        ↘ Task Repository
```

Gateway、Orchestration、Execution、Repository 和 Sensor 服务位于设备无关的控制
平面。当前 Execution 根据任务的 `device_id` 查找
`ROS_TASK_CLIENT_CONFIG` 指定的 YAML 注册表，并使用其中的 `action_name`；仓库
目前没有独立的 `adapters/` 目录；正式设备 endpoint 位于控制平面之外，
通过 ROS action 与控制平面连接，厂商 SDK 不进入上层服务。

## 目录

```text
 docs/interfaces/                     当前模块接口文档
 docs/decisions/                      当前架构决策和设计动机
docs/guide/                          使用指南、ROS mock 和设备 endpoint 指南
ros2_ws/config/devices.yaml           ROS 设备/action 注册表示例
ros2_ws/src/control_plane/            ROS task client 控制平面适配
ros2_ws/src/interfaces/               ROS action/message 接口定义
ros2_ws/src/mocks/                    mock execution 和 sensor 节点
ros2_ws/src/endpoints/                正式设备 endpoint 节点
ros2_ws/src/services/                 Rust 服务：platform、repository、sensor、
                                      execution、orchestration、gateway
webui/                                React/Vite 前端
docker/dev/                           Humble/Jazzy 开发容器配置
```

## 使用

```bash
# 选择一个 ROS 发行版。命令会构建镜像并进入交互容器
make jazzy   # Ubuntu 24.04 + ROS Jazzy
# 或 make humble  # Ubuntu 22.04 + ROS Humble

# 以下命令在容器内执行；ROS 环境必须已经由容器提供
make build
make check
make webui
make run server

# 在另一个容器终端中运行 mock endpoint
make run endpoint DEVICE_TYPE=mock-exec
make run endpoint DEVICE_TYPE=mock-sensor
make run endpoint DEVICE_TYPE=tonypi  # run on the TonyPi host only
```

`server` 和 `endpoint` 是 `run` 的两种互斥模式。服务端需要
`ROS_TASK_CLIENT_CONFIG`，但不需要 `DEVICE_TYPE`；运行 endpoint 时必须指定
`DEVICE_TYPE`。当前支持的值为 `mock-exec`、`mock-sensor` 和 `tonypi`；前两者
分别启动开发 mock，后者只应在 TonyPi 真机主机上启动
`tonypi_exec_layer_node`。
参数可通过 `ENDPOINT_ARGS` 传给 ROS 节点，例如：

```bash
make run endpoint DEVICE_TYPE=mock-exec ENDPOINT_ARGS="-p step_delay_s:=0.2"
make run endpoint DEVICE_TYPE=mock-sensor \
  ENDPOINT_ARGS="-p scenario:=anomaly -p rate_hz:=5.0 -p random_seed:=0"
```

`make build` 在容器内使用 colcon 构建 `ros2_ws/src`；在主机上则构建 Cargo
workspace。`make humble` 和 `make jazzy` 都会在镜像构建完成后进入对应的交互
容器。默认 Gateway 监听 `0.0.0.0:5000`，可通过 `GATEWAY_HTTP_PORT` 覆盖。

启动服务端默认使用相对于仓库根目录的
`ROS_TASK_CLIENT_CONFIG=ros2_ws/config/devices.yaml`。也可以在仓库根目录创建
`.env` 设置本地默认值（该文件不应提交），例如：

```dotenv
ROS_TASK_CLIENT_CONFIG=ros2_ws/config/devices.yaml
GATEWAY_HTTP_PORT=5000
```

命令行参数仍可覆盖 `.env`，例如：

```bash
make run server ROS_TASK_CLIENT_CONFIG=ros2_ws/config/production.yaml
```

`ros_task_client` 初始化时会读取、解析并校验该文件；设备 ID 和 ROS action 名称
都在 YAML 中配置。示例配置当前注册了 `mock_exec`，其 action 为
`/mock_exec/execute_task`。`mock-sensor` 是传感器 publisher，不是该注册表中的
execution device。

启动 `make webui-dev` 后，可在 <http://localhost:5173> 访问前端；Vite 会将
`/api` 和 WebSocket 请求代理到默认的 Gateway 地址 `http://127.0.0.1:5000`。

## 文档

- [文档入口](docs/README.md)
- [模块接口](docs/interfaces/README.md)
- [设计决策](docs/decisions/README.md)
- [构建与运行](docs/guide/getting-started.md)
- [ROS 2 RFC mock 指南](docs/guide/ros-mocks.md)
- [TonyPi 真机执行 endpoint](docs/guide/tonypi-exec.md)
