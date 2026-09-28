"""Run one conversational task and verify submitted robot tasks via MCP."""

import argparse
import asyncio
import json

from langchain_core.messages import AIMessage, ToolMessage

from runtime import build_agent
from settings import max_wait_seconds


def _tool_payload(content: object) -> dict:
    """Read the structured JSON returned by the current MCP tools."""
    if isinstance(content, list):
        text = next(
            (
                item.get("text")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ),
            None,
        )
    else:
        text = content
    if not isinstance(text, str):
        raise RuntimeError("MCP tool returned no JSON content")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"MCP tool failed: {text[:500]}") from error
    if not isinstance(payload, dict):
        raise RuntimeError("MCP tool returned a non-object result")
    return payload


def _submitted_tasks(messages: list) -> list[str]:
    calls = {
        call["id"]: call["name"]
        for message in messages
        if isinstance(message, AIMessage)
        for call in message.tool_calls
    }
    task_ids = []
    for message in messages:
        if not isinstance(message, ToolMessage) or calls.get(message.tool_call_id) != "create_task":
            continue
        if message.status == "error":
            raise RuntimeError(f"任务提交失败：{message.content}")
        payload = _tool_payload(message.content)
        task_ids.append(payload["task"]["id"])
    return task_ids


def _show_tool_calls(messages: list) -> None:
    for message in messages:
        if isinstance(message, AIMessage):
            for call in message.tool_calls:
                print(f"调用工具 {call['name']}：{call['args']}", flush=True)


async def _wait_for_task(tool: object, task_id: str, seconds: float) -> dict:
    loop = asyncio.get_running_loop()
    end_time = loop.time() + seconds
    previous = None
    while True:
        record = _tool_payload(await tool.ainvoke({"task_id": task_id}))
        current = (record["state"], record["progress"], record["phase"])
        if current != previous:
            print(f"任务 {task_id}：{record['state']}，进度 {record['progress']:.0%}", flush=True)
            previous = current
        if record.get("state") in ("succeeded", "failed"):
            return record
        if loop.time() >= end_time:
            return record
        await asyncio.sleep(min(1.0, end_time - loop.time()))


async def run(prompt: str) -> None:
    agent, tools = await build_agent()
    result = await agent.ainvoke(
        {"messages": [{"role": "user", "content": prompt}]},
        config={"recursion_limit": 20},
    )
    messages = result["messages"]
    _show_tool_calls(messages)
    task_ids = _submitted_tasks(messages)
    if not task_ids:
        print(messages[-1].content)
        return

    seconds = max_wait_seconds()
    for task_id in task_ids:
        print(f"任务 {task_id} 已提交，正在查询终态…", flush=True)
        record = await _wait_for_task(tools["get_task"], task_id, seconds)
        state = record["state"]
        if state in ("accepted", "running"):
            print(f"任务 {task_id} 尚未确认完成：{state}；请稍后用 get_task 查询。")
        else:
            print(f"任务 {task_id}：{state}；进度 {record['progress']:.0%}；阶段 {record['phase']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a robot task agent via the local MCP server")
    parser.add_argument("prompt", nargs="+", help="Natural-language request for the robot agent")
    args = parser.parse_args()
    try:
        asyncio.run(run(" ".join(args.prompt)))
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f"agent: {error}\n")


if __name__ == "__main__":
    main()
