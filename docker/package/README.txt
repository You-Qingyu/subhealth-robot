Docker 评审演示包使用说明

一、前提条件
1. 电脑已安装并启动 Docker Desktop（Windows，启用 Linux 容器）或 Docker Engine（Linux）。
2. 本包为 Linux amd64 镜像，无需安装 ROS 2，也无需任何源码。

二、操作步骤（Windows）
1. 解压压缩包到任意目录。
2. 双击 start.bat。
3. 脚本自动完成：缺少镜像时先从 rtos-subhealth-images.tar.gz 导入（首次约需数分钟），随后启动容器，就绪后自动打开浏览器进入演示页面。
4. 若浏览器未自动打开，手动访问 http://127.0.0.1:8080。

Linux/macOS：在本目录执行 bash start.sh，按终端打印的地址访问。

三、停止演示
在本目录执行：
    docker compose --profile agent -f compose.yaml down
或直接退出 Docker Desktop。

四、注意事项
1. Docker 必须处于运行状态；脚本检测到 Docker 未启动会显示提示并停住窗口（按任意键关闭）。
2. 首次启动需等待后端容器通过健康检查，从双击到页面打开可能需要约 1 分钟，请耐心等待。
3. 演示默认使用 mock execution（模拟执行）和 mock 生理传感器（模拟传感器数据），不连接真实机器人硬件。
4. 页面端口默认 8080。如需修改：复制 .env.example 为 .env，修改其中的 WEB_PORT，启动脚本与 Docker Compose 会读取同一份配置。
5. WebUI 的任务创建、状态查询与传感器数据展示全程在本机运行，不需要外网和任何密钥。
6. 出错时窗口会停留并显示提示，常见原因：Docker 未启动、镜像归档文件缺失或损坏。

五、可选：运行自然语言智能体
智能体已包含在镜像中，但默认不随演示启动（需要模型服务密钥）。使用步骤：
1. 复制 .env.example 为 .env，填入 OPENAI_API_KEY（AGENT_MODEL、OPENAI_BASE_URL 默认面向 DeepSeek，可按需修改）。
2. 重新执行 start.bat（或 bash start.sh）：检测到密钥后会自动启动智能体服务，WebUI 的 Agent 页面即可直接对话。
   演示已在运行时，也可在本目录执行：
    docker compose --profile agent -f compose.yaml up -d agent
3. 智能体会把该指令发送给 .env 中配置的大模型，解析为任务后下发执行。
4. 此功能需要外网和有效密钥。不配置时可忽略本节，WebUI 中Sensor、Tasks页面不受影响。
