# 快速开始

## 依赖

日常 Rust、ROS 和 WebUI 工具通过 Docker profile 提供。控制平面不要求主机
安装某一种设备 SDK。

## 格式、编译与构建

```bash
make check
make webui
```

## 运行服务端

```bash
make run server
```

服务端包含 Gateway、Orchestration、Execution 和 Sensor 控制平面，不需要传入
设备类型。

## 运行 endpoint

```bash
make run endpoint DEVICE_TYPE=<device-type>
```

开发容器中的 endpoint 支持 `mock-exec` 和 `mock-sensor`，分别启动执行 mock
和生理传感器 publisher。它们只用于开发验证，不是正式设备 adapter。

TonyPi 真机 endpoint 运行在机器人主机上，使用独立的 ROS 2 overlay；它不需要
Rust 或控制平面的服务。真机构建、DDS 配置和启动方式见
[TonyPi 真机 endpoint](tonypi-exec.md)。

## 选择镜像

```bash
make humble  # 构建 Ubuntu 22.04 + ROS Humble 镜像并进入容器
make jazzy   # 构建 Ubuntu 24.04 + ROS Jazzy 镜像并进入容器
```

## 文档入口

详见 [`docs/`](../)。历史 RFC 和迁移计划仅供参考，不再作为当前实现依据。
