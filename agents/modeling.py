"""地球科学建模智能体 (ModelingAgent)

职责：
- 空间插值（interpolate_spatial）
- 三角网构建（delaunay_triangulation）
- 等值面提取（extract_isosurface）
- 布尔运算（boolean_operation）
- 纹理贴图（apply_texture）
- 指标分级（classify_indicator）
- 属性计算（calculate_property）
"""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langgraph.prebuilt import create_react_agent

from config import LLM_PROVIDER, LLM_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE
from utils.message_compress import agent_trim_hook
from tools.modeling import (
    interpolate_spatial,
    delaunay_triangulation,
    extract_isosurface,
    boolean_operation,
    # validate_model,
    apply_texture,
    classify_indicator,
    calculate_property,
)

_TOOLS = [
    interpolate_spatial,
    delaunay_triangulation,
    extract_isosurface,
    boolean_operation,
    # validate_model,
    apply_texture,
    classify_indicator,
    calculate_property,
]

_SYSTEM_PROMPT = """你是三维空间建模系统的地球科学建模智能体（ModelingAgent）。

你的职责是基于输入数据构建三维模型，请务必遵守指令并用简洁的语言回复，你的工具包括：

1. **空间插值**：从稀疏控制点生成连续属性场（interpolate_spatial）
2. **岩性分类**：用 ML 方法预测三维岩性分布（classify_lithology）
3. **三角剖分**：对栅格DEM构造 TIN 曲面（delaunay_triangulation）
4. **等值面提取**：从属性场提取地质界面（extract_isosurface）
5. **布尔运算**：实现地质体切割、合并操作（boolean_operation）
6. **纹理贴图**：将正射影像贴到地表三角网（apply_texture）
7. **指标分级**：按 RSR/RMR/Q/GSI 等方案对属性场分级（classify_indicator）
8. **属性计算**：基于公式计算新属性（calculate_property）
"""

def create_modeling_agent(llm: BaseChatModel | None = None):
    """创建地球科学建模智能体。"""
    if llm is None:
        from llm_factory import create_llm
        llm = create_llm(provider=LLM_PROVIDER, model=LLM_MODEL or None,
                         max_tokens=LLM_MAX_TOKENS, temperature=LLM_TEMPERATURE)

    return create_react_agent(
        model=llm,
        tools=_TOOLS,
        prompt=_SYSTEM_PROMPT,
        name="ModelingAgent",
        # pre_model_hook=agent_trim_hook,
    )
