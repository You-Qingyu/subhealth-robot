# LangChain 机器人智能体

本目录提供两种运行方式，共用同一份智能体逻辑：

- **命令行**：独立运行的单轮程序，通过标准输入输出连接 MCP 服务；
- **HTTP/SSE 服务**：常驻进程，供 WebUI 的智能体页面调用。

两种方式都通过 MCP 服务访问 Gateway，不直接请求 Gateway；每次启动都会拉起
同一份 `mcp/server.py`。

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

已有的同名 shell 环境变量优先于 `.env`。

## 命令行用法

```sh
agent/.venv/bin/python agent/cli.py '让 mock_exec 依次前往 7、8、9'
```

## HTTP/SSE 服务

在仓库根目录启动（开发容器内）：

```sh
make run agent
```

等价于直接执行 `agent/.venv/bin/python agent/server.py`。服务默认只绑定
`127.0.0.1:5010`，不对局域网暴露机器人控制能力。

接口：

| 接口 | 说明 |
| --- | --- |
| `GET /agent/health` | 健康检查，返回 `{"status":"ok"}` |
| `POST /agent/chat` | 请求体 `{"prompt":"..."}`，以 SSE 流式返回整轮过程 |

SSE 事件：

| event | data 内容 |
| --- | --- |
| `tool_start` | `{"call_id","name","args"}`：开始一次工具调用 |
| `tool_result` | `{"call_id","name","status","result"}`：工具返回结果 |
| `assistant` | `{"content"}`：模型文本（可能没有） |
| `task_submitted` | `{"task_id"}`：任务已成功提交 |
| `task_state` | `{"task_id","state","progress","phase"}`：任务状态变化 |
| `done` | `{"final","tasks"}`：本轮结束 |
| `error` | `{"message"}`：本轮失败 |

用 curl 验证：

```sh
curl http://127.0.0.1:5010/agent/health
curl -N -X POST http://127.0.0.1:5010/agent/chat \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"查询当前能力"}'
```

## 配置说明

模型接口必须支持 OpenAI Compatible 工具调用。本程序使用 `ChatOpenAI`，
不复用 OpenCode 的模型配置或凭据。可选环境变量：

- `GATEWAY_URL`：Gateway 地址，默认 `http://127.0.0.1:5000`。
- `ROS_TASK_CLIENT_CONFIG`：设备注册表路径，默认仓库内的
  `ros2_ws/config/devices.yaml`。
- `AGENT_MAX_WAIT_SECONDS`：任务提交后等待终态的最长秒数，默认 60，最大 3600。
- `AGENT_HTTP_HOST`：HTTP 服务绑定地址，默认 `127.0.0.1`。
- `AGENT_HTTP_PORT`：HTTP 服务监听端口，默认 `5010`。

程序通过 MCP 的 `get_task` 查询任务，直到成功、失败或超时；`accepted`
不视为执行成功。模型也能调用 `wait_for_event`，但 Gateway 的 WebSocket
事件不会补发。命令行每次启动都是单轮会话，不持久化对话历史。

服务内部用锁串行处理请求：同一时间只运行一轮会话，避免多个请求共用一个
MCP stdio 子进程时消息交叉。

当前使用的 LangChain 内置 `langchain.mcp` 接口仍标注为 beta；
`pyproject.toml` 将依赖限制在已验证的次版本范围内。
