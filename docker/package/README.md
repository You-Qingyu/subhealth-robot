# Docker 评审演示包（实验）

此目录用于验证将 ROS 2、Rust 控制平面、mock execution 和 WebUI 封装为 Docker 镜像的交付方式。评委电脑不需要安装 ROS 2，但需要 Docker Engine；Windows 可通过 Docker Desktop 的 Linux 容器运行。

## 制作离线交付包

在有源码和网络的 Linux `amd64` 构建机上运行：

```bash
bash docker/package/build-and-export.sh
```

脚本先构建 ROS Jazzy 开发/构建镜像，再编译 ROS/Rust workspace、构建 WebUI，最后导出 `docker/package/rtos-subhealth-images.tar.gz`。也可以把归档路径作为第一个参数传给脚本。

交付给评委的目录只需包含本目录中的 `compose.yaml`、启动脚本、`.env.example` 和生成的镜像归档；不需要源码、Dockerfile 或 ROS 构建镜像。评审镜像包含 ROS runtime、已编译的 colcon install overlay、Python agent/MCP 环境和前端静态资源。

## 启动演示

Windows 双击 `start-demo.bat`；Linux/macOS 运行：

```bash
bash start-demo.sh
```

启动脚本会在本地缺少镜像时导入同目录下的压缩归档，然后创建并启动容器。浏览器访问 <http://localhost:8080>。Gateway 和 mock execution 在同一个 ROS 容器中运行，ROS DDS 不需要跨 Docker 容器或 Windows 主机发现节点。

停止演示：

```bash
docker compose -f compose.yaml down
```

归档是压缩后的 Docker image tar，不是可直接运行的容器；启动脚本用 `docker load` 导入镜像，再由 Compose 创建容器。

## 运行自然语言智能体

先复制 `.env.example` 为 `.env`，并填入模型服务要求的模型名、API 地址和密钥。然后从本目录执行：

```bash
docker compose --profile agent -f compose.yaml run --rm agent \
  '让 mock_exec 依次前往 1、2、3'
```

API key 只作为容器运行时环境变量传入，不会写入镜像。自然语言 agent 依赖外网访问配置的大模型服务；不需要自然语言交互时，WebUI 的任务创建和状态查询可以独立运行。

## 当前实验边界

- 本实验镜像目标是 Linux `amd64`、ROS 2 Jazzy；不包含原生 Windows 构建。
- 评审演示默认使用 mock execution。TonyPi endpoint 仍需在机器人侧运行并使用真实硬件 SDK、摄像头及串口。
- 只有构建机需要源码、网络和 `ros-dev:jazzy` 构建镜像。评委电脑只需要 Docker；Windows 使用 Docker Desktop 的 Linux 容器模式。
- Agent 需要外网访问模型服务和有效 API 凭据；WebUI 与 mock ROS 演示不需要模型凭据。
- 当前为实验配置，Python 依赖范围尚未锁定，基础镜像也未按 digest 固定；正式发布前应锁定依赖和镜像版本，并在目标 Windows Docker Desktop 上复验。
