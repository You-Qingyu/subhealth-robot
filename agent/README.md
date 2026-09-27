# LangChain robot agent

This is an independent, one-shot CLI agent. It discovers **the existing MCP
server's tools** over stdio; it does not call the Gateway directly. OpenCode
and this CLI start separate local instances of the same MCP server.

## Install

From the repository root (Python 3.10+):

```sh
python3 -m venv mcp/.venv
mcp/.venv/bin/python -m pip install -e ./mcp
python3 -m venv agent/.venv
agent/.venv/bin/python -m pip install -e ./agent
```

Start the Gateway and a mock execution endpoint as described in the root README.
Set the model and endpoint **in your shell** (do not commit credentials):

```sh
export AGENT_MODEL='your-tool-calling-model'
export OPENAI_API_KEY='your-key'
export OPENAI_BASE_URL='https://your-provider.example/v1'
# Optional: default is http://127.0.0.1:5000
export GATEWAY_URL='http://127.0.0.1:5000'
# Optional: default is the repository's ros2_ws/config/devices.yaml
export ROS_TASK_CLIENT_CONFIG="$PWD/ros2_ws/config/devices.yaml"
agent/.venv/bin/python agent/cli.py '让 mock_exec 依次前往 7、8、9'
```

The model endpoint must support OpenAI-compatible **tool calling**. This CLI
uses `ChatOpenAI` and does not use OpenCode's model configuration or credentials.
You can change `AGENT_MAX_WAIT_SECONDS` (default 60, maximum 3600) to limit
post-submission observation. The CLI queries `get_task` until success, failure,
or timeout; `accepted` is never reported as execution success. `wait_for_event`
is available to the model, but the Gateway's WebSocket events are not replayed.

LangChain's built-in `langchain.mcp` integration is currently marked **beta**;
the dependencies in `pyproject.toml` are bounded to the verified minor versions.
No conversation history is persisted between invocations.
