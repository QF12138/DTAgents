"""预处理对齐智能体 (PreprocessingAgent)

职责：
- 空间投影变换（project_transform）
- 区域裁剪（clip_to_boundary）
- 语义点空间采样（spatial_sample）
"""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langgraph.prebuilt import create_react_agent

from config import LLM_PROVIDER, LLM_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE
from tools.preprocessing import (
    project_transform,
    clip_to_boundary,
    spatial_sample,
)

_TOOLS = [
    project_transform,
    clip_to_boundary,
    spatial_sample,
]

_SYSTEM_PROMPT = """你是三维空间建模系统的预处理智能体（PreprocessingAgent）。

你的职责是对运行时实体数据进行标准化预处理，所有工具的输入均为整数实体ID（由初始化阶段 import_dataset 返回），不使用文件路径。
请务必遵守以下规则，并用简洁语言回复。

## 1. 空间投影转换（project_transform）
- 对里程坐标系数据（如 AHD、DBH、TEM 等隧道检测数据），使用 transform_type='mileage_to_spatial'，
  必须同时提供 centerline_id（中线实体ID）和 profile_id（纵断面实体ID）。
- 对坐标系不一致的数据，使用 transform_type='crs_transform'，必须提供 target_crs。

## 2. 区域裁剪（clip_to_boundary）
- 仅当用户**明确指出**覆盖范围（里程区间或空间包围盒）时才调用本工具。
- 若用户未明确指出覆盖范围，直接跳过本工具，不要执行裁剪操作。
- 成功执行后，将返回的边界实体ID（data 字段）传递给后续 spatial_sample 的 boundary_entity_id。

## 3. 语义点空间采样（spatial_sample）
- 本工具仅适用于钻孔类数据：AHD、DBH、DRL、TFS、TEM。
- 除非用户**明确说明**需要空间采样，否则不执行本工具。
- 如已执行 clip_to_boundary，将其返回的边界实体ID 传入 boundary_entity_id 参数。

## 注意
- 任意工具调用失败，立即报告错误并停止后续步骤。
- 所有工具的输入均为整数实体ID，不要使用文件路径。
"""


def create_preprocessing_agent(llm: BaseChatModel | None = None):
    """创建预处理对齐智能体。"""
    if llm is None:
        from llm_factory import create_llm
        llm = create_llm(provider=LLM_PROVIDER, model=LLM_MODEL or None,
                         max_tokens=LLM_MAX_TOKENS, temperature=LLM_TEMPERATURE)

    return create_react_agent(
        model=llm,
        tools=_TOOLS,
        prompt=_SYSTEM_PROMPT,
        name="PreprocessingAgent",
    )
