"""规划协调器 (Planner Agent / Supervisor)

职责：
- 理解用户的自然语言建模指令
- 将任务分解为有序的子任务
- 将子任务路由到合适的专业智能体
- 管理共享状态和工作流编排
- 错误恢复与重试策略
"""
from __future__ import annotations

from langchain_core.language_models import BaseChatModel
from langgraph_supervisor import create_supervisor

from config import LLM_PROVIDER, LLM_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE
from agents.initialization import create_initialization_agent
# from agents.preprocessing import create_preprocessing_agent
from agents.modeling import create_modeling_agent
from agents.visualization import create_visualization_agent
# from utils.message_compress import supervisor_trim_hook

# - **PreprocessingAgent**（预处理）：负责裁剪、体素化、标准化、空间采样、去噪滤波

_SUPERVISOR_PROMPT = """你是三维空间建模系统的规划协调器（Planner）。
你的职责是理解用户的建模需求，将任务分解并移交给正确的专业智能体，
请严格按智能体能力分工，无需额外拓展，务必遵守指令并用简洁的语言回复：
## 可用智能体
- **InitializationAgent**（初始化）：负责工程层级检索、数据查询检索、数据读取和导入加载
- **ModelingAgent**（三维建模）：负责三角网建模、纹理贴图、空间插值、机器学习、属性融合
- **VisualizationAgent**（集成可视化）：负责场景渲染、相机控制、剖切视图、统计图表

你必须先输出一段文本，明确说明：
1. 用户总体需求是什么。
2. 你决定将任务拆分成哪些部分。
3. 接下来你将把哪部分任务交给哪个智能体。

写完这段分析和分配说明后，再执行转移（Transfer)

最后总结阶段请务必保持语言简练准确，不要罗列详细数据
"""


def create_geo_modeling_system(llm: BaseChatModel | None = None) -> object:
    """
    创建三维空间建模多智能体系统。

    Args:
        llm: 已初始化的 LLM 实例（由 llm_factory.create_llm 创建）。
             为 None 时使用环境变量配置自动构建。

    Returns:
        已编译的 LangGraph 工作流图，可直接调用 .invoke() 或 .stream()
    """
    if llm is None:
        from llm_factory import create_llm
        llm = create_llm(
            provider=LLM_PROVIDER,
            model=LLM_MODEL or None,
            max_tokens=LLM_MAX_TOKENS,
            temperature=LLM_TEMPERATURE,
        )

    # 创建各专业智能体
    data_agent = create_initialization_agent(llm)
    # prep_agent = create_preprocessing_agent(llm)
    model_agent = create_modeling_agent(llm)
    viz_agent = create_visualization_agent(llm)

    # 创建 Supervisor 图
    # output_mode="last_message"（默认值）：子 Agent 只将最终答案追加到共享 state，
    # 不返回内部工具调用链，防止 parent state 因单次任务爆炸式增长。
    # pre_model_hook：在 supervisor 每次 LLM 调用前裁剪过长的旧消息，
    # 防止 context window 溢出（不影响 parent state 的实际存储）。
    graph = create_supervisor(
        # agents=[data_agent, prep_agent, model_agent, viz_agent],
        agents=[data_agent, model_agent, viz_agent],
        model=llm,
        prompt=_SUPERVISOR_PROMPT,
        output_mode="last_message"
    )

    return graph.compile()
