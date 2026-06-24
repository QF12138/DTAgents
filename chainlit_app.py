"""Chainlit 网页界面入口 - 三维空间建模多智能体系统"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import chainlit as cl
from chainlit.config import config

config.run.headless = True

from langchain_core.messages import AIMessage, HumanMessage

from config import LANGGRAPH_RECURSION_LIMIT, LLM_DEBUG, LLM_MAX_TOKENS, LLM_TEMPERATURE
from utils.message_compress import compress_history_async, estimate_tokens
from utils.dt_runtime import configure_dt_runtime
from database import db

logger = logging.getLogger(__name__)

configure_dt_runtime()


def _get_env(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


@cl.on_chat_start
async def on_chat_start() -> None:
    """初始化 LLM 和多智能体系统，存入会话。"""
    provider  = _get_env("DTG_PROVIDER", "anthropic")
    api_key   = _get_env("DTG_API_KEY") or None
    model     = _get_env("DTG_MODEL") or None
    base_url  = _get_env("DTG_BASE_URL") or None
    _reasoning_env = _get_env("DTG_REASONING")
    reasoning: bool | None = True if _reasoning_env == "true" else (False if _reasoning_env == "false" else None)

    if provider != "ollama" and not api_key:
        await cl.Message(content="[错误] 未检测到 API Key，请通过 `--api-key` 或环境变量提供。").send()
        return

    # 初始化数据库
    db.connect()
    logger.info("数据库初始化完成")

    from llm_factory import create_llm
    llm = create_llm(
        provider=provider,
        model=model,
        api_key=api_key,
        base_url=base_url,
        max_tokens=LLM_MAX_TOKENS,
        temperature=LLM_TEMPERATURE,
        reasoning=reasoning,
        debug=LLM_DEBUG,
    )
    model_name = getattr(llm, "model_name", None) or getattr(llm, "model", "unknown")
    logger.info("LLM: %s / %s", provider, model_name)

    from agents.planner import create_geo_modeling_system
    logger.info("正在初始化多智能体系统...")
    app = create_geo_modeling_system(llm=llm)

    cl.user_session.set("app", app)
    cl.user_session.set("llm", llm)
    cl.user_session.set("history", [])   # 多轮对话历史


@cl.on_message
async def on_message(msg: cl.Message) -> None:
    """接收用户消息，压缩历史后调用多智能体系统，流式返回结果。"""
    agents = ["supervisor", "InitializationAgent", "PreprocessingAgent",
              "ModelingAgent", "VisualizationAgent"]

    app = cl.user_session.get("app")
    llm = cl.user_session.get("llm")
    if app is None or llm is None:
        await cl.Message(content="[错误] 系统未初始化，请刷新页面重试。").send()
        return

    history: list = cl.user_session.get("history", [])

    # ── 压缩检查 ──────────────────────────────────────────────
    token_before = estimate_tokens(history)
    history = await compress_history_async(llm, history)
    token_after = estimate_tokens(history)
    if token_after < token_before:
        logger.info("历史已压缩 | token %d → %d", token_before, token_after)

    # ── 构造本轮输入 ──────────────────────────────────────────
    # 将压缩后的历史 + 当前用户消息一起传入 Agent
    input_messages = history + [("user", msg.content)]

    # ── 流式执行 ─────────────────────────────────────────────
    steps: dict = {}
    answer = cl.Message(content="")

    async with cl.Step(name="VGEDT Agents"):
        async for event in app.astream_events(
            {"messages": input_messages},
            config={"recursion_limit": LANGGRAPH_RECURSION_LIMIT},
            version="v2",
        ):
            name  = event["name"]
            kind  = event["event"]
            parents = event["parent_ids"]

            if kind == "on_chat_model_stream":
                content = event["data"]["chunk"].content
                if content:
                    await answer.stream_token(content)

            elif kind == "on_chain_start" and name in agents and len(parents) == 1:
                async with cl.Step(id=event["run_id"]) as step:
                    step.name = name

            elif kind == "on_tool_start":
                async with cl.Step(
                    name=name,
                    language="text",
                    show_input="json",
                    parent_id=parents[1] if len(parents) > 1 else None,
                ) as step:
                    param = event["data"].get("input")
                    step.input = None if param == {} else param
                    steps[event["run_id"]] = step

            elif kind == "on_tool_end":
                step = steps.get(event["run_id"])
                if step:
                    step.output = event["data"].get("output")
                    await step.send()

    await answer.send()

    # ── 更新历史 ─────────────────────────────────────────────
    history.append(HumanMessage(content=msg.content))
    if answer.content:
        history.append(AIMessage(content=answer.content))
    cl.user_session.set("history", history)

    logger.info(
        "历史更新 | 当前条数=%d, 估算token=%d",
        len(history), estimate_tokens(history),
    )


@cl.on_chat_end
async def on_chat_end() -> None:
    """会话结束时关闭数据库连接。"""
    try:
        db.close()
    except Exception:
        pass
