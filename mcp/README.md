# Local MCP for the Gateway

This directory contains an MCP server exposing **all current Gateway endpoints**:

| MCP tool | Gateway source |
| --- | --- |
| `list_tasks` | `GET /api/v1/tasks` |
| `create_task` | `POST /api/v1/tasks` |
| `get_task` | `GET /api/v1/tasks/{id}` |
| `wait_for_event` | `GET /api/v1/events` (WebSocket, next live event) |
| `list_capabilities` | Locally configured devices and primitives |

`wait_for_event` subscribes when called; events before subscription cannot be
recovered. `get_task` is the source of truth for task status. Gateway currently
has no cancel endpoint or device/primitive listing endpoint.

## Configuration

- `ROS_TASK_CLIENT_CONFIG`: **required**, the same `devices.yaml` used by the
  Gateway. Enabled devices are reread from this file for capability listing and
  task submission. Edit that registry to add or disable devices.
- `MCP_CONFIG_PATH`: optional, defaults to `mcp/config.yaml`. Its `primitives`
  list controls which primitive names MCP exposes and permits. **The backend
  must also implement a primitive**; currently it only supports `go_to_tag`.
- `GATEWAY_URL`: optional HTTP(S) origin; defaults to `http://127.0.0.1:5000`.

Run the Gateway and an endpoint first (see the root README). From the project
root, create the local Python 3.10+ environment and install the dependencies:

```sh
python3 -m venv mcp/.venv
mcp/.venv/bin/python -m pip install -e ./mcp
opencode mcp list
```

The checked-in `opencode.jsonc` starts this environment as a local MCP stdio
server named `robot`. It uses `ros2_ws/config/devices.yaml` unless OpenCode
inherits `ROS_TASK_CLIENT_CONFIG`; use the **same registry** as the Gateway.
Change `GATEWAY_URL` in the project config if the Gateway listens elsewhere.
If you do not use
OpenCode, run `mcp/.venv/bin/python mcp/server.py` under another MCP host.
Keep protocol output on stdout; write diagnostics to stderr.

The server connects to the
Gateway on the host running OpenCode; when the Gateway runs inside Docker,
publish its port to the host. Do not send tasks to an untrusted Gateway.
