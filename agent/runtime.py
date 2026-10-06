"""Create the LangChain agent from the current MCP tool catalog."""

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
不要声称已完成未确认的执行，也不要无请求地重复提交任务。"""


async def build_agent() -> tuple[object, dict]:
    """Discover MCP tools and return an agent plus the task-query tool."""
    values = model_settings()
    async with MCPAdapter(mcp_config()) as adapter:
        tools = await adapter.list_tools()
    names = {tool.name for tool in tools}
    required = {
        "list_capabilities", "list_tags", "list_tasks", "get_task", "create_task",
        "wait_for_event",
    }
    if not required <= names:
        raise RuntimeError(f"MCP server is missing tools: {sorted(required - names)}")

    model = ChatOpenAI(
        model=values["AGENT_MODEL"],
        api_key=values["OPENAI_API_KEY"],
        base_url=values["OPENAI_BASE_URL"],
        use_responses_api=False,
    )
    return create_agent(model=model, tools=tools, system_prompt=SYSTEM_PROMPT), {
        tool.name: tool for tool in tools
    }
