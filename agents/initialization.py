"""初始化智能体 (InitializationAgent)

职责：
- 工程层级查询（query_hierarchy）
- 元数据查询（query_metadata）
- 数据读取（import_dataset）
- 数据验证（validate_data）
"""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langgraph.prebuilt import create_react_agent

from config import (
    LLM_PROVIDER, LLM_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE
)
from utils.message_compress import agent_trim_hook
from tools.initialization import (
    query_metadata,
    query_hierarchy,
    import_dataset,
    # validate_data,
)

_TOOLS = [
    # 工程层级管理
    query_hierarchy,
    # 数据集管理
    query_metadata,
    import_dataset,
    # # 数据验证
    # validate_data,
]

_SYSTEM_PROMPT = """你是三维空间建模系统的初始化智能体（InitializationAgent）。
职责：分析需求确认工具链，按需执行工程层级查询、数据集检索、数据读取加载。
请务必注意，可能需要多次调用工具，务必确认所有任务均已完成后再退出

## 第一步：确认工程层级信息（query_hierarchy）
- 按工程名检索，调用 query_hierarchy(level='project') 获取工程列表，匹配工程名称得到 project_id。
- 当用户明确指定具体工点时，才进一步调用 query_hierarchy(level='work_site', project_id=...) 获取 site_ids。
- 按里程信息检索，如（DK5+268），可直接调用 query_hierarchy(level='work_site', mileage_infos=...)，获取 site_ids 以及 mileage_range。
- 若工具提示未找到匹配的工程或工点信息，告知用户并停止。

## 第二步：检索数据集（query_metadata）
- 根据不同层级传入 project_id 或 site_ids，以及用户指定的 data_type、mileage_range、time_range。
- 对于里程定位类型数据（TSP/TEM/GPR/AHD/DBH/TFR/TBM/RDR/IST/EMS），工具会自动在 metadata.auxiliary_data 中附加辅助信息。
- 检索后立即报告：
  - 找到数据（≤阈值）：列出每条数据的名称、类型、文件路径、描述信息；如有 auxiliary_data 则一并告知中线/纵断面数据信息。
  - 结果超出阈值：工具已返回按类型汇总的统计，直接转告用户并请确认或缩小范围，不要自行继续加载。
  - 未找到数据：明确告知并停止。

## 第三步：读取数据（import_dataset）
- 当用户明确指出"加载"、"读取"、"导入"时调用，只有"检索/查询/查找"在第二步完成后立即停止。
- 同时请注意如果有辅助数据 metadata.auxiliary_data 也需要一并读取和加载。
- 读取完成后汇报：成功加载的数量及各数据集的类型和实体 ID。

## 注意
- 任意工具调用失败，立即报告错误并停止后续步骤。
- 建模任务不属于本职责，回复中说明需由 ModelingAgent 处理。
- 如果不能执行或存在任何问题，请务必说明情况。
"""

# ## 数据验证（validate_data）
# 数据检索成功后验证，quality_flag=3时，明确报告问题并直接终止所有对话

# ## 坐标系统转换（project_transform）
# 统一使用工程定义的坐标系统，如果导入数据与该坐标系不一致则需要转换，否则不需要

def create_initialization_agent(llm: BaseChatModel | None = None):
    """创建初始化智能体。"""
    if llm is None:
        from llm_factory import create_llm
        llm = create_llm(provider=LLM_PROVIDER, model=LLM_MODEL or None,
                         max_tokens=LLM_MAX_TOKENS, temperature=LLM_TEMPERATURE)

    return create_react_agent(
        model=llm,
        tools=_TOOLS,
        prompt=_SYSTEM_PROMPT,
        name="InitializationAgent",
        # pre_model_hook=agent_trim_hook,
    )
