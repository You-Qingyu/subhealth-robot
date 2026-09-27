# LangChain 机器人智能体

本目录提供独立运行的单轮命令行智能体。它通过标准输入输出连接现有 MCP 服务，
不直接请求 Gateway。OpenCode 和本命令行程序会分别启动同一份 MCP 服务。

## 安装

在仓库根目录执行（需要 Python 3.10 或更高版本）：

```sh
python3 -m venv mcp/.venv
mcp/.venv/bin/python -m pip install -e ./mcp
python3 -m venv agent/.venv
agent/.venv/bin/python -m pip install -e ./agent
```

先按照根目录 `README.md` 启动 Gateway 和模拟执行节点。在 `agent/.env`
中配置模型和接口地址；该文件会自动加载，且已被 Git 忽略。例如 DeepSeek
V4.1 Flash 的配置格式如下，密钥请填自己的值：

```dotenv
AGENT_MODEL=deepseek-flash
OPENAI_API_KEY=your-key
OPENAI_BASE_URL=https://api.deepseek.com
```

已有的同名 shell 环境变量优先于 `.env`。运行示例：

```sh
agent/.venv/bin/python agent/cli.py '让 mock_exec 依次前往 7、8、9'
```

模型接口必须支持 OpenAI Compatible 工具调用。本程序使用 `ChatOpenAI`，
不复用 OpenCode 的模型配置或凭据。可选环境变量：

- `GATEWAY_URL`：Gateway 地址，默认 `http://127.0.0.1:5000`。
- `ROS_TASK_CLIENT_CONFIG`：设备注册表路径，默认仓库内的
  `ros2_ws/config/devices.yaml`。
- `AGENT_MAX_WAIT_SECONDS`：任务提交后等待终态的最长秒数，默认 60，最大 3600。

程序通过 MCP 的 `get_task` 查询任务，直到成功、失败或超时；`accepted` 不视为执行成功。
模型也能调用 `wait_for_event`，但 Gateway 的 WebSocket 事件不会补发。
每次启动都是单轮会话，不持久化对话历史。

当前使用的 LangChain 内置 `langchain.mcp` 接口仍标注为 beta；
`pyproject.toml` 将依赖限制在已验证的次版本范围内。
