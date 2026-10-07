"""智能体的 HTTP/SSE 入口；浏览器通过 Vite 代理访问。"""

import asyncio
import contextlib
import json
from collections.abc import AsyncGenerator

from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
from starlette.requests import Request

from conversation import run_turn
from runtime import AgentRuntime
from settings import agent_http_host, agent_http_port

SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}

MAX_PROMPT_LENGTH = 2000


def sse_event(name: str, payload: dict) -> str:
    """序列化一条 SSE 事件。"""
    data = json.dumps(payload, ensure_ascii=False)
    return f"event: {name}\ndata: {data}\n\n"


def error_response(status: int, code: str, message: str) -> JSONResponse:
    """构造与 Gateway 错误格式一致的 JSON 响应。"""
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message}},
    )


class ChatRequest(BaseModel):
    prompt: str


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """启动时构建智能体，关闭时释放 MCP 连接。"""
    runtime = AgentRuntime()
    await runtime.start()
    app.state.runtime = runtime
    try:
        yield
    finally:
        await runtime.close()


app = FastAPI(title="ROS Subhealth Agent", lifespan=lifespan)


@app.get("/agent/health")
async def health() -> dict:
    return {"status": "ok"}


@app.post("/agent/chat")
async def chat(request: Request, body: ChatRequest):
    prompt = body.prompt.strip()
    if not prompt:
        return error_response(422, "invalid_prompt", "prompt must not be empty")
    if len(prompt) > MAX_PROMPT_LENGTH:
        return error_response(
            422,
            "invalid_prompt",
            f"prompt must be at most {MAX_PROMPT_LENGTH} characters",
        )
    runtime: AgentRuntime = request.app.state.runtime
    return StreamingResponse(
        _event_stream(runtime, prompt),
        media_type="text/event-stream",
        headers=SSE_HEADERS,
    )


async def _event_stream(runtime: AgentRuntime, prompt: str):
    """把 run_turn 的事件通过队列转为 SSE 流。"""
    queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()

    async def emit(name: str, payload: dict) -> None:
        await queue.put((name, payload))

    turn = asyncio.create_task(run_turn(runtime, prompt, emit))
    try:
        while not turn.done():
            getter = asyncio.create_task(queue.get())
            finished, _ = await asyncio.wait(
                {turn, getter}, return_when=asyncio.FIRST_COMPLETED
            )
            if getter in finished:
                name, payload = getter.result()
                yield sse_event(name, payload)
            else:
                getter.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await getter
        while not queue.empty():
            name, payload = queue.get_nowait()
            yield sse_event(name, payload)
        failure = turn.exception()
        if failure is not None:
            yield sse_event("error", {"message": str(failure)})
    except asyncio.CancelledError:
        turn.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await turn
        raise


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=agent_http_host(),
        port=agent_http_port(),
        log_level="info",
    )
