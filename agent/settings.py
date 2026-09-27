"""Configuration for the independent LangChain CLI and its local MCP process."""

import os
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def model_settings() -> dict[str, str]:
    names = ("AGENT_MODEL", "OPENAI_API_KEY", "OPENAI_BASE_URL")
    values = {name: os.environ.get(name, "").strip() for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise ValueError(f"Set the model environment variables: {', '.join(missing)}")
    return values


def mcp_config() -> dict:
    """Start the existing MCP server in its own environment over stdio."""
    configured_registry = os.environ.get("ROS_TASK_CLIENT_CONFIG") or str(
        ROOT / "ros2_ws/config/devices.yaml"
    )
    registry = Path(configured_registry).expanduser().resolve()
    if not registry.is_file():
        raise ValueError(f"ROS_TASK_CLIENT_CONFIG file does not exist: {registry}")
    python = ROOT / "mcp/.venv/bin/python"
    if not python.is_file():
        raise ValueError("Install the MCP dependencies in mcp/.venv first (see agent/README.md)")
    return {
        "mcpServers": {
            "robot": {
                "command": str(python),
                "args": [str(ROOT / "mcp/server.py")],
                "env": {
                    "ROS_TASK_CLIENT_CONFIG": str(registry),
                    "GATEWAY_URL": os.environ.get("GATEWAY_URL", "http://127.0.0.1:5000"),
                },
            }
        }
    }


def max_wait_seconds() -> float:
    value = float(os.environ.get("AGENT_MAX_WAIT_SECONDS", "60"))
    if not 0 < value <= 3600:
        raise ValueError("AGENT_MAX_WAIT_SECONDS must be greater than 0 and at most 3600")
    return value
