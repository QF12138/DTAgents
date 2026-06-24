"""可视化智能体 (VisualizationAgent)

职责：
- 实体外观控制（configure_entity）
- 体素模型切片（set_voxel_slice）
- 视图布局管理（create_view）
- 标准视角切换（set_standard_view）
- 相机聚焦（focus_on_entity）
"""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langgraph.prebuilt import create_react_agent

from config import LLM_PROVIDER, LLM_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE
from tools.visualization import (
    configure_entity,
    set_voxel_slice,
    # create_view,
    set_standard_view,
    focus_on_entity,
)

_TOOLS = [
    configure_entity,
    set_voxel_slice,
    # create_view,
    set_standard_view,
    focus_on_entity,
]

_SYSTEM_PROMPT = """你是三维空间建模系统的可视化智能体（VisualizationAgent）。
通过工具调用直接控制 DTGeoStudio 软件内置的视图面板。

## 工具说明

- configure_entity   设置实体外观，可一次控制可见性、渲染模式、透明度（任意组合）
- set_voxel_slice    为体素模型设置切片面，查看内部地质结构
- set_standard_view  切换标准视角（top / front / right / isometric 等）
- focus_on_entity    自动将相机 fit 至目标实体，orbit=True 时设置轨道旋转中心

"""


def create_visualization_agent(llm: BaseChatModel | None = None):
    """创建可视化智能体。"""
    if llm is None:
        from llm_factory import create_llm
        llm = create_llm(provider=LLM_PROVIDER, model=LLM_MODEL or None,
                         max_tokens=LLM_MAX_TOKENS, temperature=LLM_TEMPERATURE)

    return create_react_agent(
        model=llm,
        tools=_TOOLS,
        prompt=_SYSTEM_PROMPT,
        name="VisualizationAgent",
    )
