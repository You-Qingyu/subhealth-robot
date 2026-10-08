# Docker 评审演示包（实验）

此目录用于验证将 ROS 2、Rust 控制平面、mock execution 和 WebUI 封装为 Docker 镜像的交付方式。评委电脑不需要安装 ROS 2，但需要 Docker Engine；Windows 可通过 Docker Desktop 的 Linux 容器运行。

## 制作离线交付包

在有源码和网络的 Linux `amd64` 构建机上运行：

```bash
bash docker/package/build-and-export.sh
```

脚本先构建 ROS Jazzy 开发/构建镜像，再编译 ROS/Rust workspace、构建 WebUI，最后导出 `docker/package/rtos-subhealth-images.tar.gz`。也可以把归档路径作为第一个参数传给脚本。

构建时 ROS apt 源默认写入官方源和若干镜像源（USTC、阿里、南大、哈工大），apt 会逐个回退，只要还有可用源就继续构建。需要用固定源保证可复现时，传入 `ROS_APT_MIRROR=<源地址>`，例如 `ROS_APT_MIRROR=https://mirrors.ustc.edu.cn/ros2/ubuntu bash docker/package/build-and-export.sh`。

交付给评委的目录只需包含本目录中的 `compose.yaml`、启动脚本、`.env.example`、`README.txt` 和生成的镜像归档；不需要源码、Dockerfile、`README.md` 或 ROS 构建镜像。评审镜像包含 ROS runtime、已编译的 colcon install overlay、Python agent/MCP 环境和前端静态资源。

在构建机上把交付文件打成 zip（评委说明用 `README.txt`，不放本文件）：

```bash
cd docker/package
zip rtos-subhealth-demo.zip compose.yaml start-demo.sh start-demo.bat .env.example README.txt rtos-subhealth-images.tar.gz
```

`zip` 只会新增或替换包内条目、不会删除已存在的条目，所以重新打包前必须先删掉旧 zip，否则早前版本放进包里的文件（如 `README.md`）会残留在新 zip 中。打包前确认 `rtos-subhealth-images.tar.gz` 已由 `build-and-export.sh` 生成，可用 `unzip -l rtos-subhealth-demo.zip` 检查包内清单是否恰好是上述 6 个文件。

## 启动演示

Windows 双击 `start-demo.bat`；Linux/macOS 运行：

```bash
bash start-demo.sh
```

启动脚本会在本地缺少镜像时导入同目录下的压缩归档，然后创建并启动容器。Windows 双击 `start-demo.bat` 后会自动在浏览器打开 <http://127.0.0.1:8080>；Linux/macOS 运行 `start-demo.sh` 后按打印的地址访问，建议在 Windows 浏览器中打开（WSL 环境内可能无法加载）。端口依次取环境变量 `WEB_PORT`、`.env` 中的 `WEB_PORT`，默认 `8080`。Gateway 和 mock execution 在同一个 ROS 容器中运行，ROS DDS 不需要跨 Docker 容器或 Windows 主机发现节点。

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
