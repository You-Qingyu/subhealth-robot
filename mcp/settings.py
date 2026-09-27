"""Load MCP capabilities from configuration shared with the ROS task client."""

import os
from pathlib import Path

import yaml
from mcp.server.mcpserver.exceptions import ToolError


MCP_CONFIG_PATH = Path(__file__).with_name("config.yaml")


def _read_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as error:
        raise ToolError(f"Cannot load configuration {path}: {error}") from error
    if not isinstance(data, dict):
        raise ToolError(f"Configuration {path} must be a mapping")
    return data


def capabilities() -> dict[str, list[str]]:
    """Return enabled devices and exposed primitives; reread files on each call."""
    registry_path = os.environ.get("ROS_TASK_CLIENT_CONFIG")
    if not registry_path:
        raise ToolError("Set ROS_TASK_CLIENT_CONFIG to the Gateway's devices.yaml")

    registry = _read_yaml(Path(registry_path))
    settings = _read_yaml(Path(os.environ.get("MCP_CONFIG_PATH", MCP_CONFIG_PATH)))
    entries = registry.get("devices")
    primitives = settings.get("primitives")
    if not isinstance(entries, list) or not isinstance(primitives, list):
        raise ToolError("Configuration requires devices and primitives lists")

    devices = []
    for entry in entries:
        if (
            not isinstance(entry, dict)
            or not isinstance(entry.get("id"), str)
            or not isinstance(entry.get("enabled"), bool)
        ):
            raise ToolError("Each device needs a string id and boolean enabled flag")
        if entry["enabled"]:
            devices.append(entry["id"])
    if any(not isinstance(value, str) or not value for value in primitives):
        raise ToolError("Each primitive must be a nonempty string")
    if len(set(devices)) != len(devices) or len(set(primitives)) != len(primitives):
        raise ToolError("Device and primitive names must be unique")
    return {"devices": devices, "primitives": primitives}
