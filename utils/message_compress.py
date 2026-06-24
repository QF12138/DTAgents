"""消息摘要压缩工具

提供两级压缩策略：
- 条数触发：历史消息条数 ≥ MSG_COMPRESS_THRESHOLD
- Token 触发：估算 token 数 ≥ TOKEN_COMPRESS_THRESHOLD（强制压缩）

压缩结果：将旧消息合并为一条摘要 SystemMessage，
保留末尾 MSG_KEEP_RECENT 条原始消息不压缩，
保证 LLM 仍能感知最近的上下文。
"""
from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage, SystemMessage, RemoveMessage

from config import (
    MSG_COMPRESS_THRESHOLD, TOKEN_COMPRESS_THRESHOLD, MSG_KEEP_RECENT,
    SUPERVISOR_CTX_CHARS, AGENT_CTX_CHARS,
)

logger = logging.getLogger(__name__)

# 摘要请求的提示词
_SUMMARIZE_SYSTEM = (
    "你是一个对话历史摘要助手。请将以下多轮对话历史压缩为简洁的摘要，"
    "重点保留：已查询/加载的数据集信息、已执行的建模操作、关键参数、"
    "中间结果的文件路径或实体ID、以及尚未完成的任务。"
    "摘要使用中文，控制在 200 字以内。"
)

_SUMMARIZE_HUMAN = "请对以下对话历史进行摘要：\n\n{history_text}"


# ─────────────────────────────────────────────────────────────
# Token 估算
# ─────────────────────────────────────────────────────────────
def _content_str(msg: dict | BaseMessage | tuple) -> str:
    """从多种消息格式中提取文本内容。"""
    if isinstance(msg, tuple):
        return str(msg[1]) if len(msg) > 1 else ""
    if isinstance(msg, dict):
        content = msg.get("content", "")
    else:
        content = getattr(msg, "content", "")
    if isinstance(content, list):
        # 多模态消息：提取所有 text 块
        return " ".join(
            block.get("text", "") if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content)


def estimate_tokens(messages: list) -> int:
    """粗略估算消息列表的 token 数（1 token ≈ 1 字符）。"""
    total_chars = sum(len(_content_str(m)) for m in messages)
    return total_chars


def needs_compression(messages: list) -> bool:
    """判断是否需要压缩。"""
    if len(messages) >= MSG_COMPRESS_THRESHOLD:
        return True
    if estimate_tokens(messages) >= TOKEN_COMPRESS_THRESHOLD:
        return True
    return False


# ─────────────────────────────────────────────────────────────
# 摘要生成
# ─────────────────────────────────────────────────────────────
def _format_history_text(messages: list) -> str:
    """将消息列表格式化为可读文本，供摘要 LLM 总结。"""
    lines = []
    for msg in messages:
        if isinstance(msg, tuple):
            role, content = msg[0], (msg[1] if len(msg) > 1 else "")
        elif isinstance(msg, dict):
            role = msg.get("role", "unknown")
            content = _content_str(msg)
        elif isinstance(msg, HumanMessage):
            role, content = "用户", _content_str(msg)
        elif isinstance(msg, AIMessage):
            role, content = "AI", _content_str(msg)
        elif isinstance(msg, SystemMessage):
            role, content = "系统", _content_str(msg)
        else:
            role, content = type(msg).__name__, _content_str(msg)
        # 跳过空内容（如工具调用消息）
        if not content.strip():
            continue
        lines.append(f"[{role}]: {content[:500]}")  # 单条截断防止过长
    return "\n".join(lines)


async def summarize_messages_async(
    llm: BaseChatModel,
    messages: list,
) -> str:
    """异步调用 LLM 生成对话历史摘要。"""
    history_text = _format_history_text(messages)
    if not history_text.strip():
        return ""
    prompt = [
        SystemMessage(content=_SUMMARIZE_SYSTEM),
        HumanMessage(content=_SUMMARIZE_HUMAN.format(history_text=history_text)),
    ]
    response = await llm.ainvoke(prompt)
    return _content_str(response)


def summarize_messages_sync(
    llm: BaseChatModel,
    messages: list,
) -> str:
    """同步调用 LLM 生成对话历史摘要（CLI 模式使用）。"""
    history_text = _format_history_text(messages)
    if not history_text.strip():
        return ""
    prompt = [
        SystemMessage(content=_SUMMARIZE_SYSTEM),
        HumanMessage(content=_SUMMARIZE_HUMAN.format(history_text=history_text)),
    ]
    response = llm.invoke(prompt)
    return _content_str(response)


# ─────────────────────────────────────────────────────────────
# 压缩入口
# ─────────────────────────────────────────────────────────────
async def compress_history_async(
    llm: BaseChatModel,
    history: list,
) -> list:
    """
    异步压缩历史消息。

    策略：
    1. 若 history 不需要压缩，原样返回。
    2. 将末尾 MSG_KEEP_RECENT 条消息之前的部分送给 LLM 做摘要。
    3. 返回 [SystemMessage(摘要)] + 末尾 MSG_KEEP_RECENT 条消息。

    Args:
        llm:     LLM 实例，用于生成摘要。
        history: 当前全量历史消息列表。

    Returns:
        压缩后的消息列表。
    """
    if not needs_compression(history):
        return history

    system_msgs, other_msgs = _split_system_messages(history)

    keep = MSG_KEEP_RECENT
    to_summarize = other_msgs[:-keep] if len(other_msgs) > keep else []
    recent = other_msgs[-keep:] if len(other_msgs) > keep else other_msgs

    if not to_summarize:
        return history

    token_before = estimate_tokens(history)
    logger.info(
        "触发消息压缩 | 总条数=%d, 估算token=%d, 压缩前%d条, 保留%d条, 保护系统消息%d条",
        len(history), token_before, len(to_summarize), len(recent), len(system_msgs),
    )

    try:
        summary_text = await summarize_messages_async(llm, to_summarize)
    except Exception as e:
        logger.warning("消息摘要生成失败，跳过压缩: %s", e)
        return history

    summary_msg = SystemMessage(content=f"[对话历史摘要]\n{summary_text}")
    # 保留原有系统消息 → 新摘要 → 最近对话
    compressed = system_msgs + [summary_msg] + recent

    logger.info(
        "消息压缩完成 | 压缩后条数=%d, 估算token=%d → %d",
        len(compressed), token_before, estimate_tokens(compressed),
    )
    return compressed


# ─────────────────────────────────────────────────────────────
# Graph 内部 pre_model_hook：剪裁 Agent 内部 state 消息
# ─────────────────────────────────────────────────────────────
def make_trim_hook(max_chars: int, keep_recent: int = 8):
    """
    创建一个 LangGraph pre_model_hook，在每次 LLM 调用前
    通过 RemoveMessage 删除超出上限的旧消息。

    适用于 supervisor 和各子 Agent 的 create_react_agent(pre_model_hook=...)
    以及 create_supervisor(pre_model_hook=...) 参数。

    工作原理：
    - 仅修改 Agent 内部 state，NOT 影响 parent graph 的共享 state。
    - 配合 output_mode="last_message"（默认值），parent state 每轮仅
      追加 1 条最终答案，整体增长已受控。
    - hook 负责防止单次 LLM 调用因历史过长而超出 context window。

    Args:
        max_chars:   消息字符总数上限，超过则裁剪（1 字符 ≈ 1 token）。
        keep_recent: 裁剪后保留的最近消息条数（不可删除尾部消息）。

    Returns:
        pre_model_hook callable，签名为 (state: dict) -> dict。
    """
    def _hook(state: dict) -> dict:
        messages: list = state.get("messages", [])
        
        if not messages:
            return {}
        
        # 根据 tokens 数量判断是否需要裁剪
        total_chars = estimate_tokens(messages)
        if total_chars <= max_chars:
            return {}

        # 根据 messages 数量判断是否需要裁剪
        if len(messages) <= keep_recent:
            return {}
        
        # 分离 system 消息
        system_messages = []
        other_messages = []
    
        for msg in messages:
            if isinstance(msg, SystemMessage):
                system_messages.append(msg)
            else:
                other_messages.append(msg)
        
        to_remove = []
        removed_messages = []

        for m in other_messages:
            # 1. 如果是工具返回的原始数据，删掉
            if isinstance(m, ToolMessage):
                to_remove.append(RemoveMessage(id=m.id))
                removed_messages.append(m)
            # 2. 如果是 Agent 决定调用工具的那条思考记录，删掉
            elif isinstance(m, AIMessage) and m.tool_calls:
                logger.info(m)
                to_remove.append(RemoveMessage(id=m.id))
                removed_messages.append(m)

        if not to_remove:
            return {}
        
        remove_chars = estimate_tokens(removed_messages)

        logger.info(
            "pre_model_hook 裁剪 | 删除 %d 条旧消息，当前共 %d 条，包括 %d 条系统提示词信息，估算删除字符 %d ，剩余字符 %d ", 
            len(to_remove), len(messages) - len(to_remove), len(system_messages), remove_chars, total_chars - remove_chars,
        )
        
        # return {"messages": to_remove}

        return {}

    return _hook


# 预构建实例，供各 Agent 直接导入使用
supervisor_trim_hook = make_trim_hook(max_chars=SUPERVISOR_CTX_CHARS, keep_recent=12)
agent_trim_hook      = make_trim_hook(max_chars=AGENT_CTX_CHARS,      keep_recent=8)


def _split_system_messages(messages: list) -> tuple[list, list]:
    """将消息列表拆分为 (系统消息列表, 非系统消息列表)。

    系统消息（SystemMessage 或 role=='system' 的 dict）不参与摘要压缩，
    始终保留在历史最前端。
    """
    system_msgs: list = []
    other_msgs: list = []
    for msg in messages:
        is_system = (
            isinstance(msg, SystemMessage)
            or (isinstance(msg, dict) and msg.get("role") == "system")
        )
        if is_system:
            system_msgs.append(msg)
        else:
            other_msgs.append(msg)
    return system_msgs, other_msgs


def compress_history_sync(
    llm: BaseChatModel,
    history: list,
) -> list:
    """
    同步压缩历史消息（CLI 模式使用）。

    逻辑与 compress_history_async 相同，使用同步 LLM 调用。

    保护策略：
    - SystemMessage（系统提示词、历史摘要）始终置于结果最前，不纳入摘要范围。
    - 仅对 Human/AI/Tool 消息做条数/token 触发压缩。
    """
    if not needs_compression(history):
        return history

    system_msgs, other_msgs = _split_system_messages(history)

    keep = MSG_KEEP_RECENT
    to_summarize = other_msgs[:-keep] if len(other_msgs) > keep else []
    recent = other_msgs[-keep:] if len(other_msgs) > keep else other_msgs

    if not to_summarize:
        return history

    token_before = estimate_tokens(history)
    logger.info(
        "触发消息压缩 | 总条数=%d, 估算token=%d, 压缩前%d条, 保留%d条, 保护系统消息%d条",
        len(history), token_before, len(to_summarize), len(recent), len(system_msgs),
    )

    try:
        summary_text = summarize_messages_sync(llm, to_summarize)
    except Exception as e:
        logger.warning("消息摘要生成失败，跳过压缩: %s", e)
        return history

    summary_msg = SystemMessage(content=f"[对话历史摘要]\n{summary_text}")
    # 保留原有系统消息 → 新摘要 → 最近对话
    compressed = system_msgs + [summary_msg] + recent

    logger.info(
        "消息压缩完成 | 压缩后条数=%d, 估算token=%d → %d",
        len(compressed), token_before, estimate_tokens(compressed),
    )
    return compressed
