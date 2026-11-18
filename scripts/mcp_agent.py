"""Agentic client: LangChain ChatOllama driving tools over MCP.

Connects to app/mcp/server.py over stdio, bridges its MCP tools into
LangChain StructuredTool objects (hand-rolled — langchain-mcp-adapters
doesn't yet support mcp>=2.0), binds them to ChatOllama, and runs a manual
tool-calling loop so each decision the model makes is visible.

Usage:
    python3 -m scripts.mcp_agent "What's the risk level for account 123456?"
    python3 -m scripts.mcp_agent   # interactive prompt
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import StructuredTool
from langchain_ollama import ChatOllama
from mcp import types
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

from app.config import settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
MAX_TURNS = 5

SYSTEM_PROMPT = (
    "You are a KYC/AML compliance assistant for ZPTPL analysts. You have a "
    "tool, get_merchant_kyc_details, that looks up a merchant's live "
    "KYC/risk profile in Payments Detective by numeric account_id. Call it "
    "when the user asks about a specific account. If the tool result "
    "contains an 'error' field, relay that error to the user plainly "
    "instead of inventing an answer."
)


def _unwrap_tool_result(result: types.CallToolResult) -> object:
    if result.structured_content is not None:
        return result.structured_content
    for block in result.content:
        text = getattr(block, "text", None)
        if text is not None:
            try:
                return json.loads(text)
            except ValueError:
                return text
    return None


def _bridge_tool(session: ClientSession, tool: types.Tool) -> StructuredTool:
    async def _call(**kwargs: object) -> object:
        result = await session.call_tool(tool.name, kwargs)
        return _unwrap_tool_result(result)

    return StructuredTool.from_function(
        coroutine=_call,
        name=tool.name,
        description=tool.description or "",
        args_schema=tool.input_schema,
    )


async def _ask(session: ClientSession, tools: list[StructuredTool], question: str) -> str:
    tools_by_name = {t.name: t for t in tools}
    llm = ChatOllama(model=settings.chat_model, base_url=settings.ollama_host, temperature=0).bind_tools(tools)

    messages = [SystemMessage(SYSTEM_PROMPT), HumanMessage(question)]
    for _ in range(MAX_TURNS):
        ai_msg = await llm.ainvoke(messages)
        messages.append(ai_msg)
        if not ai_msg.tool_calls:
            return ai_msg.content
        for call in ai_msg.tool_calls:
            tool = tools_by_name[call["name"]]
            result = await tool.ainvoke(call["args"])
            messages.append(ToolMessage(content=json.dumps(result), tool_call_id=call["id"]))
    return f"Gave up after {MAX_TURNS} tool-call turns without a final answer."


async def run(question: str) -> str:
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "app.mcp.server"],
        cwd=str(PROJECT_ROOT),
    )
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            mcp_tools = (await session.list_tools()).tools
            tools = [_bridge_tool(session, t) for t in mcp_tools]
            return await _ask(session, tools, question)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ask the Payments Detective MCP agent a question.")
    parser.add_argument("question", nargs="*", help="Question to ask (omit for interactive mode)")
    args = parser.parse_args()

    if args.question:
        print(asyncio.run(run(" ".join(args.question))))
        return

    while True:
        try:
            question = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question or question.lower() in {"exit", "quit"}:
            break
        print(asyncio.run(run(question)))


if __name__ == "__main__":
    main()
