"""Local MCP tools for the current Gateway interface."""

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from gateway_client import next_event, request, task_path
from settings import capabilities


mcp = MCPServer("ros-subhealth")


@mcp.tool()
def list_capabilities() -> dict:
    """List enabled device IDs and configured task primitives before creating a task.

    Devices come from the ROS task client's registry; primitives are the subset
    exposed by the MCP configuration, not a promise of new backend behavior.
    """
    return capabilities()


@mcp.tool()
async def list_tasks() -> list:
    """List all Gateway task records (the Gateway currently has no pagination)."""
    return await request("GET", "/api/v1/tasks")


@mcp.tool()
async def get_task(task_id: str) -> dict:
    """Get the authoritative task state, progress and phase by task ID."""
    return await request("GET", task_path(task_id))


@mcp.tool()
async def create_task(
    device_id: str,
    primitive: str,
    target: list[int],
    deadline_ms: int | None = None,
) -> dict:
    """Submit a task; 202/accepted does not mean that execution has succeeded.

    Use list_capabilities first. Target is an ordered list of integer tags for
    go_to_tag. The Gateway validates each primitive's actual payload support.
    """
    allowed = capabilities()
    if device_id not in allowed["devices"]:
        raise ToolError(f"Device {device_id!r} is not enabled; use list_capabilities")
    if primitive not in allowed["primitives"]:
        raise ToolError(f"Primitive {primitive!r} is not exposed; use list_capabilities")
    if not isinstance(target, list) or not target or any(type(tag) is not int for tag in target):
        raise ToolError("target must be a nonempty list of integer tags")
    if deadline_ms is not None and (type(deadline_ms) is not int or deadline_ms < 0):
        raise ToolError("deadline_ms must be a nonnegative Unix epoch millisecond value")

    payload = {
        "device_id": device_id,
        "primitive": primitive,
        "target": target,
        "deadline_ms": deadline_ms,
    }
    return await request("POST", "/api/v1/tasks", payload)


@mcp.tool()
async def wait_for_event(timeout_seconds: float = 20.0) -> dict:
    """Subscribe to /api/v1/events and return the next live WebSocket event.

    Events are not replayed: a change occurring before this call subscribes is
    lost. Use get_task to check the authoritative state after a missed event.
    """
    return await next_event(timeout_seconds)


if __name__ == "__main__":
    mcp.run(transport="stdio")
