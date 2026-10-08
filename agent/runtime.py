"""管理 LangChain 智能体及其 MCP 连接的生命周期。"""

import asyncio
import sys

from langchain.agents import create_agent
from langchain.mcp import MCPAdapter
from langchain_openai import ChatOpenAI

from settings import mcp_config, model_settings


SYSTEM_PROMPT = """你是机器人任务助手，只能使用已提供的 MCP 工具操作机器人。
设备和原语必须先通过 list_capabilities 查询，不要猜测或硬编码设备能力。
用户以地点名称指定目标时，先用 list_tags 查询名称对应的 Tag ID；无法确定目标时再询问用户。
当前 go_to_tag 的 target 是按执行顺序排列的整数标签；不要自行规划地图路径，由 Gateway 补全路线。
调用 create_task 后，accepted 仅表示接收，不代表完成。提交后停止；调用方会查询最终状态。
查询任务时只根据 get_task 返回的记录说明状态；事件可能丢失，不作为最终状态依据。
传感器数据先用 list_sensors 发现，再用 read_sensor 读取最新值；sample 为 null 表示尚未收到数据，不要臆测数值。
不要声称已完成未确认的执行，也不要无请求地重复提交任务。"""

REQUIRED_TOOLS = {
    "list_capabilities",
    "list_tags",
    "list_tasks",
    "get_task",
    "create_task",
    "wait_for_event",
    "list_sensors",
    "read_sensor",
}


class AgentRuntime:
    """持有常驻 MCPAdapter、智能体和工具表，随宿主进程启停。"""

    def __init__(self) -> None:
        self.adapter: MCPAdapter | None = None
        self.agent: object | None = None
        self.tools: dict[str, object] = {}
        self.turn_lock = asyncio.Lock()

    async def start(self) -> None:
        """启动 MCP 连接并构建智能体；失败时清理已启动的子进程。"""
        if self.agent is not None:
            return
        values = model_settings()
        adapter = MCPAdapter(mcp_config())
        await adapter.__aenter__()
        try:
            tools = await adapter.list_tools()
            names = {tool.name for tool in tools}
            missing = REQUIRED_TOOLS - names
            if missing:
                raise RuntimeError(
                    f"MCP server is missing tools: {sorted(missing)}"
                )
            model = ChatOpenAI(
                model=values["AGENT_MODEL"],
                api_key=values["OPENAI_API_KEY"],
                base_url=values["OPENAI_BASE_URL"],
                use_responses_api=False,
            )
            self.agent = create_agent(
                model=model, tools=tools, system_prompt=SYSTEM_PROMPT
            )
            self.tools = {tool.name: tool for tool in tools}
            self.adapter = adapter
        except BaseException:
            await adapter.__aexit__(*sys.exc_info())
            raise

    async def close(self) -> None:
        """幂等关闭 MCP 连接并清空智能体状态。"""
        adapter = self.adapter
        self.adapter = None
        self.agent = None
        self.tools = {}
        if adapter is not None:
            await adapter.__aexit__(None, None, None)

    def require_agent(self) -> object:
        """返回已启动的智能体，未启动时显式报错。"""
        if self.agent is None:
            raise RuntimeError("agent runtime has not been started")
        return self.agent
