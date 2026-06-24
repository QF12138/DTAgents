"""
评测指标计算模块

指标定义：
  单智能体：
    TSA  - Tool Selection Accuracy（工具选择准确率）
    PA   - Parameter Accuracy（参数精确率）
    TCF1 - Tool Call F1（工具调用 F1）
    TSR  - Task Success Rate（任务完成率）
    STC  - Steps-to-Completion efficiency（步骤效率）
    HAL  - Hallucination Rate（幻觉参数率）

  多智能体：
    PRA  - Planner Routing Accuracy（Planner 路由准确率）
    SCR  - Subtask Completion Rate（子任务完成率）
    CO   - Communication Overhead（通信开销）
    E2E  - End-to-End Success Rate
    E2E_L - End-to-End Latency (seconds)
    TOK  - Token Usage
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from tests.eval_framework.scorer import ParamMatchResult


# ── 单次用例运行结果 ───────────────────────────────────────────────────────────

@dataclass
class ToolCallRecord:
    """单次工具调用的记录"""
    tool_name: str
    params: dict[str, Any]
    response: dict[str, Any]              # 工具返回（Mock 或真实）
    param_match: ParamMatchResult | None = None  # 参数比对结果（后填充）


@dataclass
class CaseResult:
    """单条测试用例的运行结果"""
    case_id: str
    case_name: str
    agent: str
    level: str
    prompt: str

    # 实际调用记录
    actual_tool_calls: list[ToolCallRecord] = field(default_factory=list)
    # 期望调用序列（工具名列表）
    expected_tools: list[str] = field(default_factory=list)
    expected_steps: int = 1

    # 终态
    final_success: bool = False       # 最终工具是否成功
    reached_expected_state: bool = False

    # 延迟 & Token
    latency_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0

    # 路由信息（多智能体）
    routed_agents: list[str] = field(default_factory=list)
    expected_agents: list[str] = field(default_factory=list)

    # 错误信息
    error: str | None = None

    # ── 计算属性 ──────────────────────────────────────────────────────────────

    @property
    def actual_tools(self) -> list[str]:
        return [r.tool_name for r in self.actual_tool_calls]

    @property
    def tsa(self) -> float:
        """工具选择准确率：期望工具中被正确调用的比例"""
        if not self.expected_tools:
            return 1.0
        hits = sum(1 for t in self.expected_tools if t in self.actual_tools)
        return hits / len(self.expected_tools)

    @property
    def tcf1(self) -> float:
        """工具调用 F1（基于工具名集合）"""
        expected_set = set(self.expected_tools)
        actual_set = set(self.actual_tools)
        if not expected_set and not actual_set:
            return 1.0
        tp = len(expected_set & actual_set)
        precision = tp / len(actual_set) if actual_set else 0.0
        recall = tp / len(expected_set) if expected_set else 0.0
        if precision + recall == 0:
            return 0.0
        return 2 * precision * recall / (precision + recall)

    @property
    def pa(self) -> float:
        """参数精确率：所有已比对工具调用的平均 PA"""
        scores = [r.param_match.param_accuracy
                  for r in self.actual_tool_calls
                  if r.param_match is not None]
        return sum(scores) / len(scores) if scores else 1.0

    @property
    def hal(self) -> float:
        """幻觉参数率：所有工具调用中幻觉字段的平均率"""
        scores = [r.param_match.hallucination_rate
                  for r in self.actual_tool_calls
                  if r.param_match is not None]
        return sum(scores) / len(scores) if scores else 0.0

    @property
    def stc(self) -> float:
        """步骤效率：期望步骤数 / 实际步骤数（越接近 1 越好，>1 意味着少走了步骤）"""
        actual = len(self.actual_tool_calls)
        if actual == 0:
            return 0.0
        return min(self.expected_steps / actual, 1.0)

    @property
    def tsr(self) -> float:
        """任务完成率：0 或 1（本条用例级别）"""
        return 1.0 if self.reached_expected_state else 0.0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    # 多智能体
    @property
    def pra(self) -> float:
        """Planner 路由准确率"""
        if not self.expected_agents:
            return 1.0
        hits = sum(1 for a in self.expected_agents if a in self.routed_agents)
        return hits / len(self.expected_agents)


# ── 批量聚合 ───────────────────────────────────────────────────────────────────

@dataclass
class AggregatedMetrics:
    """一组用例（按 agent / level / provider 筛选）的聚合指标"""
    label: str            # 描述标签（如 "InitializationAgent / L2"）
    provider: str = ""
    model: str = ""
    agent_filter: str = ""
    level_filter: str = ""

    case_count: int = 0

    # 单智能体均值
    avg_tsa: float = 0.0
    avg_pa: float = 0.0
    avg_tcf1: float = 0.0
    avg_tsr: float = 0.0
    avg_stc: float = 0.0
    avg_hal: float = 0.0

    # 多智能体均值
    avg_pra: float = 0.0

    # 效率
    avg_latency_s: float = 0.0
    avg_total_tokens: float = 0.0

    # 原始数据
    cases: list[CaseResult] = field(default_factory=list, repr=False)

    @classmethod
    def from_cases(
        cls,
        cases: list[CaseResult],
        label: str = "",
        provider: str = "",
        model: str = "",
        agent_filter: str = "",
        level_filter: str = "",
    ) -> "AggregatedMetrics":
        m = cls(label=label, provider=provider, model=model,
                agent_filter=agent_filter, level_filter=level_filter,
                cases=cases, case_count=len(cases))
        if not cases:
            return m

        def _avg(fn) -> float:
            vals = [fn(c) for c in cases]
            return sum(vals) / len(vals)

        m.avg_tsa = _avg(lambda c: c.tsa)
        m.avg_pa = _avg(lambda c: c.pa)
        m.avg_tcf1 = _avg(lambda c: c.tcf1)
        m.avg_tsr = _avg(lambda c: c.tsr)
        m.avg_stc = _avg(lambda c: c.stc)
        m.avg_hal = _avg(lambda c: c.hal)
        m.avg_pra = _avg(lambda c: c.pra)
        m.avg_latency_s = _avg(lambda c: c.latency_s)
        m.avg_total_tokens = _avg(lambda c: float(c.total_tokens))
        return m

    def as_dict(self) -> dict:
        return {
            "label": self.label,
            "provider": self.provider,
            "model": self.model,
            "case_count": self.case_count,
            "TSA": round(self.avg_tsa, 4),
            "PA": round(self.avg_pa, 4),
            "TCF1": round(self.avg_tcf1, 4),
            "TSR": round(self.avg_tsr, 4),
            "STC": round(self.avg_stc, 4),
            "HAL": round(self.avg_hal, 4),
            "PRA": round(self.avg_pra, 4),
            "AVG_TOKENS": round(self.avg_total_tokens),
            "AVG_LATENCY_S": round(self.avg_latency_s, 2),
        }
