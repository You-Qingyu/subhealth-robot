# Gateway 本地 MCP 服务

本目录的 MCP 服务覆盖 Gateway **目前所有对外入口**：

| MCP 工具 | Gateway 入口 |
| --- | --- |
| `list_tags` | `GET /api/v1/tags`（返回 Tag ID 与地点名称，不含边和权重） |
| `list_tasks` | `GET /api/v1/tasks` |
| `create_task` | `POST /api/v1/tasks` |
| `get_task` | `GET /api/v1/tasks/{id}` |
| `wait_for_event` | `GET /api/v1/events`（WebSocket，等待下一条实时事件） |
| `list_capabilities` | 从本地配置读取设备和原语 |

`wait_for_event` 调用时才订阅，无法获取之前的事件；任务状态以 `get_task` 为准。
Gateway 目前没有取消任务、列出设备或列出原语的接口。

## 配置

- `ROS_TASK_CLIENT_CONFIG`：必填，与 Gateway 使用同一份 `devices.yaml`。
  MCP 服务每次列出能力或提交任务时都会重新读取已启用的设备。
- `MCP_CONFIG_PATH`：可选，默认 `mcp/config.yaml`。其中的 `primitives`
  列表决定 MCP 允许暴露和提交哪些原语；**后端仍须实现相应原语**。
  当前后端只支持 `go_to_tag`。
- `GATEWAY_URL`：可选，默认 `http://127.0.0.1:5000`。

先按照仓库根目录 `README.md` 启动 Gateway 和执行节点。在仓库根目录安装依赖：

```sh
python3 -m venv mcp/.venv
mcp/.venv/bin/python -m pip install -e ./mcp
opencode mcp list
```

需要 Python 3.10 或更高版本。项目级 `opencode.jsonc` 会以名为 `robot` 的
本地 MCP 服务启动 `mcp/.venv`，通过标准输入输出通信。默认使用
`ros2_ws/config/devices.yaml`；如果 OpenCode 继承了 `ROS_TASK_CLIENT_CONFIG`，
则使用该变量指定的文件。应确保它和 Gateway 读取的是**同一份注册表**。
Gateway 地址不同时，在 `opencode.jsonc` 中修改 `GATEWAY_URL`。

不使用 OpenCode 时，也可以从其他 MCP 客户端启动
`mcp/.venv/bin/python mcp/server.py`。标准输出用于 MCP 协议，诊断日志应写入标准错误。
MCP 服务会连接运行 OpenCode 所在主机的 Gateway；如果 Gateway 在 Docker 容器内，
需要将端口发布到主机。只向可信任的 Gateway 提交任务。
