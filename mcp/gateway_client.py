"""Access the Gateway HTTP endpoints and its live WebSocket event stream."""

import asyncio
import json
import os
from urllib.parse import quote, urlsplit

import httpx
import websockets
from mcp.server.mcpserver.exceptions import ToolError


class GatewayError(ToolError):
    """A Gateway request failed or the event stream was unavailable."""


def base_url() -> str:
    value = os.environ.get("GATEWAY_URL", "http://127.0.0.1:5000").rstrip("/")
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or parsed.path not in ("", "/"):
        raise GatewayError("GATEWAY_URL must be an HTTP(S) origin, e.g. http://127.0.0.1:5000")
    return value


async def request(method: str, path: str, payload: dict | None = None) -> dict | list:
    try:
        async with httpx.AsyncClient(base_url=base_url(), timeout=10.0) as client:
            response = await client.request(method, path, json=payload)
            response.raise_for_status()
            return response.json()
    except httpx.HTTPStatusError as error:
        raise GatewayError(
            f"Gateway returned HTTP {error.response.status_code}: {error.response.text[:500]}"
        ) from error
    except (httpx.RequestError, ValueError) as error:
        raise GatewayError(f"Gateway request failed: {error}") from error


def task_path(task_id: str) -> str:
    if not task_id:
        raise GatewayError("task_id must not be empty")
    return f"/api/v1/tasks/{quote(task_id, safe='')}"


def sensor_path(sensor_id: str) -> str:
    if not sensor_id:
        raise GatewayError("sensor_id must not be empty")
    return f"/api/v1/sensors/{quote(sensor_id, safe='')}"


async def next_event(timeout_seconds: float) -> dict:
    """Receive one live event; the Gateway does not retain or replay events."""
    if not 0 < timeout_seconds <= 60:
        raise GatewayError("timeout_seconds must be greater than 0 and at most 60")
    origin = base_url()
    scheme = "wss://" if origin.startswith("https://") else "ws://"
    url = scheme + origin.split("://", 1)[1] + "/api/v1/events"
    try:
        async with websockets.connect(url, open_timeout=10) as socket:
            message = await asyncio.wait_for(socket.recv(), timeout=timeout_seconds)
            return json.loads(message)
    except TimeoutError:
        return {"status": "timeout", "message": "No event arrived while subscribed"}
    except (OSError, websockets.WebSocketException, ValueError) as error:
        raise GatewayError(f"Gateway event stream failed: {error}") from error
