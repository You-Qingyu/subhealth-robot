"""运行一轮智能体会话，并把过程与任务终态作为事件发出。"""

import asyncio
import json
from collections.abc import Awaitable, Callable

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    ToolMessage,
)

from runtime import AgentRuntime
from settings import max_wait_seconds


Emit = Callable[[str, dict], Awaitable[None]]

TERMINAL_STATES = {"succeeded", "failed"}

RESULT_PREVIEW_LIMIT = 1000


def content_text(content: object) -> str:
    """从字符串或内容块列表中取出文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        return "".join(parts)
    return ""


def parse_content(content: object) -> object:
    """解析工具返回的 JSON；无法解析时抛出 RuntimeError。"""
    text = content_text(content)
    if not text:
        raise RuntimeError("MCP tool returned no JSON content")
    try:
        return json.loads(text)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"MCP tool failed: {text[:500]}") from error


def parse_object(content: object) -> dict:
    """解析工具返回的 JSON 对象。"""
    payload = parse_content(content)
    if not isinstance(payload, dict):
        raise RuntimeError("MCP tool returned a non-object result")
    return payload


def describe_content(content: object) -> object:
    """tool_result 展示用：能解析给 JSON，否则给截断的原始文本。"""
    try:
        return parse_content(content)
    except RuntimeError:
        text = content_text(content)
        return text[:RESULT_PREVIEW_LIMIT] if text else None


def message_text(message: BaseMessage) -> str:
    """取出消息中的文本内容。"""
    return content_text(getattr(message, "content", ""))


def iter_messages(update: object) -> list[BaseMessage]:
    """从不同 stream 版本的 update 结构中防御式提取消息。"""
    if isinstance(update, BaseMessage):
        return [update]
    if isinstance(update, list):
        return [
            message
            for item in update
            for message in iter_messages(item)
        ]
    if isinstance(update, dict):
        messages: list[BaseMessage] = []
        for value in update.values():
            messages.extend(iter_messages(value))
        return messages
    return []


def _call_name(messages: list[BaseMessage], call_id: str) -> str:
    """根据工具调用 ID 找到调用的工具名。"""
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        for call in message.tool_calls:
            if call["id"] == call_id:
                return call["name"]
    return ""


def _created_task_id(message: ToolMessage) -> str | None:
    """从 create_task 的工具结果中取出任务 ID。"""
    try:
        payload = parse_object(message.content)
    except RuntimeError:
        return None
    task = payload.get("task")
    if isinstance(task, dict) and isinstance(task.get("id"), str):
        return task["id"]
    return None


def _message_fingerprint(message: BaseMessage) -> str:
    """内容感知的去重指纹：同 ID 但内容不同时视为新消息，避免丢弃增量更新。"""
    parts = [type(message).__name__, str(getattr(message, "id", ""))]
    if isinstance(message, AIMessage):
        parts.append(message_text(message))
        parts.extend(call["id"] for call in message.tool_calls)
    elif isinstance(message, ToolMessage):
        parts.append(str(message.tool_call_id))
        parts.append(message_text(message))
    return "|".join(parts)


async def _ingest(
    message: BaseMessage,
    messages: list[BaseMessage],
    seen_fingerprints: set[str],
    seen_tool_calls: set[str],
    seen_tool_results: set[str],
    emit: Emit,
) -> None:
    """将一条新消息加入累积列表，并发出对应的会话事件。"""
    fingerprint = _message_fingerprint(message)
    if fingerprint in seen_fingerprints:
        return
    seen_fingerprints.add(fingerprint)
    messages.append(message)

    if isinstance(message, AIMessage):
        text = message_text(message)
        if text:
            await emit("assistant", {"content": text})
        for call in message.tool_calls:
            call_id = call.get("id")
            if not isinstance(call_id, str) or call_id in seen_tool_calls:
                continue
            seen_tool_calls.add(call_id)
            await emit(
                "tool_start",
                {
                    "call_id": call_id,
                    "name": call["name"],
                    "args": call.get("args", {}),
                },
            )
    elif isinstance(message, ToolMessage):
        tool_call_id = message.tool_call_id
        if tool_call_id in seen_tool_results:
            return
        seen_tool_results.add(tool_call_id)
        name = _call_name(messages, message.tool_call_id)
        status = getattr(message, "status", "success")
        await emit(
            "tool_result",
            {
                "call_id": message.tool_call_id,
                "name": name,
                "status": status,
                "result": describe_content(message.content),
            },
        )
        if name == "create_task" and status != "error":
            task_id = _created_task_id(message)
            if task_id is not None:
                await emit("task_submitted", {"task_id": task_id})


async def _drive_agent(
    runtime: AgentRuntime,
    prompt: str,
    emit: Emit,
) -> list[BaseMessage]:
    """流式驱动智能体并累积完整消息。

    只走 astream 一条路径：模型或工具出错时由 run_turn 捕获并发出
    error 事件，绝不自动重试，避免重复调用模型或重复提交任务。
    """
    agent = runtime.require_agent()
    user_message = HumanMessage(content=prompt)
    messages: list[BaseMessage] = [user_message]
    seen_fingerprints: set[str] = set()
    seen_tool_calls: set[str] = set()
    seen_tool_results: set[str] = set()

    stream = agent.astream(
        {"messages": [user_message]},
        config={"recursion_limit": 20},
        stream_mode="updates",
    )
    async for update in stream:
        for message in iter_messages(update):
            await _ingest(
                message,
                messages,
                seen_fingerprints,
                seen_tool_calls,
                seen_tool_results,
                emit,
            )
    return messages


def _submitted_ids(messages: list[BaseMessage]) -> list[str]:
    """按 ToolMessage 顺序提取 create_task 成功提交的任务 ID，并去重。"""
    call_names: dict[str, str] = {}
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                call_names[call["id"]] = call["name"]

    task_ids: list[str] = []
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        if call_names.get(message.tool_call_id) != "create_task":
            continue
        if getattr(message, "status", "success") == "error":
            continue
        task_id = _created_task_id(message)
        if task_id is not None and task_id not in task_ids:
            task_ids.append(task_id)
    return task_ids


async def _poll_task(
    runtime: AgentRuntime,
    task_id: str,
    emit: Emit,
) -> dict:
    """轮询 get_task 直到终态或超时，状态变化时发出 task_state。"""
    get_task = runtime.tools["get_task"]
    loop = asyncio.get_running_loop()
    deadline = loop.time() + max_wait_seconds()
    previous: tuple[object, object, object] | None = None
    while True:
        record = parse_object(await get_task.ainvoke({"task_id": task_id}))
        state = record["state"]
        progress = record["progress"]
        phase = record["phase"]
        current = (state, progress, phase)
        if current != previous:
            await emit(
                "task_state",
                {
                    "task_id": task_id,
                    "state": state,
                    "progress": progress,
                    "phase": phase,
                },
            )
            previous = current
        if state in TERMINAL_STATES or loop.time() >= deadline:
            return record
        await asyncio.sleep(1.0)


def _final_text(messages: list[BaseMessage]) -> str:
    """取最后一条不带工具调用的 AI 文本作为结束语。"""
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not message.tool_calls:
            text = message_text(message)
            if text:
                return text
    return ""


async def run_turn(runtime: AgentRuntime, prompt: str, emit: Emit) -> None:
    """运行一轮会话：驱动智能体、确认任务终态、发出 done/error。"""
    async with runtime.turn_lock:
        try:
            messages = await _drive_agent(runtime, prompt, emit)
            tasks = []
            for task_id in _submitted_ids(messages):
                record = await _poll_task(runtime, task_id, emit)
                tasks.append(
                    {
                        "task_id": task_id,
                        "state": record["state"],
                        "progress": record["progress"],
                        "phase": record["phase"],
                    }
                )
            await emit(
                "done",
                {"final": _final_text(messages), "tasks": tasks},
            )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await emit("error", {"message": str(error)})
