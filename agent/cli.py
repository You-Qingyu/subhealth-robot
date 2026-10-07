"""单轮命令行智能体：通过本地 MCP 服务操作机器人并查询终态。"""

import argparse
import asyncio

from conversation import run_turn
from runtime import AgentRuntime


async def _print_done(payload: dict) -> None:
    """打印结束语以及每个任务的终态。"""
    if payload["final"]:
        print(payload["final"], flush=True)
    for task in payload["tasks"]:
        if task["state"] in ("accepted", "running"):
            print(
                f"任务 {task['task_id']} 尚未确认完成：{task['state']}；"
                "请稍后用 get_task 查询。",
                flush=True,
            )
        else:
            print(
                f"任务 {task['task_id']}：{task['state']}；"
                f"进度 {task['progress']:.0%}；阶段 {task['phase']}",
                flush=True,
            )


async def _print_event(
    name: str, payload: dict, failures: list[str]
) -> None:
    """把会话事件打印为命令行输出；error 事件记录失败原因。"""
    if name == "tool_start":
        print(f"调用工具 {payload['name']}：{payload['args']}", flush=True)
    elif name == "assistant":
        print(payload["content"], flush=True)
    elif name == "task_submitted":
        print(f"任务 {payload['task_id']} 已提交，正在查询终态…", flush=True)
    elif name == "task_state":
        print(
            f"任务 {payload['task_id']}：{payload['state']}，"
            f"进度 {payload['progress']:.0%}",
            flush=True,
        )
    elif name == "done":
        await _print_done(payload)
    elif name == "error":
        failures.append(payload["message"])


async def run(prompt: str) -> None:
    runtime = AgentRuntime()
    await runtime.start()
    failures: list[str] = []
    try:
        async def emit(name: str, payload: dict) -> None:
            await _print_event(name, payload, failures)

        await run_turn(runtime, prompt, emit)
    finally:
        await runtime.close()
    if failures:
        raise RuntimeError(failures[0])


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a robot task agent via the local MCP server"
    )
    parser.add_argument(
        "prompt",
        nargs="+",
        help="Natural-language request for the robot agent",
    )
    args = parser.parse_args()
    try:
        asyncio.run(run(" ".join(args.prompt)))
    except (ValueError, RuntimeError, OSError) as error:
        parser.exit(1, f"agent: {error}\n")


if __name__ == "__main__":
    main()
