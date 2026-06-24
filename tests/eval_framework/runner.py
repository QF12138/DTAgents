"""
测试执行器

职责：
1. 加载 YAML 测试用例
2. 拦截工具调用（Mock 模式：用 Mock 返回替换真实工具）
3. 驱动智能体运行并收集 ToolCallRecord
4. 填充 CaseResult（TSA、PA、STC、TSR 等）
5. 返回 CaseResult 列表供 reporter 聚合

Mock 拦截原理：
  在 LangChain/LangGraph 工具层面，通过替换工具函数的 __call__ 为 Mock 版本，
  在工具被调用时记录参数并返回预设的 Mock 响应，同时不执行真实逻辑。
"""
from __future__ import annotations

import time
import traceback
from pathlib import Path
from typing import Any

import yaml

from tests.eval_framework.metrics import CaseResult, ToolCallRecord
from tests.eval_framework.scorer import compare_tool_call
from tests.fixtures.mock_tools import MOCK_DB, get_mock_response


# ── YAML 用例加载 ──────────────────────────────────────────────────────────────

def load_case(yaml_path: str | Path) -> dict:
    with open(yaml_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_cases_for_agent(
    agent: str,
    level_filter: list[str] | None = None,
    cases_dir: str | Path | None = None,
) -> list[dict]:
    """
    加载指定 agent 的所有测试用例。

    Args:
        agent:         "initialization" | "modeling" | "visualization" | "multi_agent"
        level_filter:  ["L1","L2"] 等，None 表示全部
        cases_dir:     测试用例根目录，默认为 tests/test_cases/
    """
    if cases_dir is None:
        cases_dir = Path(__file__).parent.parent / "test_cases"
    agent_dir = Path(cases_dir) / agent
    if not agent_dir.exists():
        return []

    cases = []
    for yaml_file in sorted(agent_dir.glob("*.yaml")):
        case = load_case(yaml_file)
        if level_filter and case.get("level") not in level_filter:
            continue
        cases.append(case)
    return cases


# ── Mock 工具拦截器 ────────────────────────────────────────────────────────────

class MockToolInterceptor:
    """
    拦截智能体的工具调用，返回 Mock 响应并记录调用参数。

    使用方式：
        interceptor = MockToolInterceptor(case_mock_responses)
        with interceptor.patch(agent_tools):
            result = agent.invoke(...)
        records = interceptor.records
    """

    def __init__(self, mock_responses: dict[str, dict] | None = None):
        """
        Args:
            mock_responses: 用例级别的 mock 覆盖（来自 YAML 的 mock_responses 字段）
        """
        self._case_mocks = mock_responses or {}
        self.records: list[ToolCallRecord] = []

    def make_mock_fn(self, tool_name: str, original_fn):
        """生成拦截函数：记录调用参数，返回 Mock 响应。"""
        interceptor = self

        def mock_fn(**kwargs):
            # 选择 mock 响应（优先用例级别 > 全局默认）
            case_mock = interceptor._case_mocks.get(tool_name)
            if case_mock:
                response = case_mock
            else:
                # 根据参数特征选择合适的 scenario
                scenario = interceptor._pick_scenario(tool_name, kwargs)
                response = get_mock_response(tool_name, scenario)

            record = ToolCallRecord(
                tool_name=tool_name,
                params=dict(kwargs),
                response=response,
            )
            interceptor.records.append(record)
            # LangChain 工具期望返回字符串或字典
            import json
            return json.dumps(response, ensure_ascii=False)

        return mock_fn

    def _pick_scenario(self, tool_name: str, params: dict) -> str:
        """根据参数智能选择 mock scenario。"""
        if tool_name == "query_hierarchy":
            level = params.get("level", "project")
            if level == "project":
                return "project_list"
            mileage = params.get("mileage_infos")
            if mileage:
                return "work_site_by_mileage"
            return "work_site_list"

        if tool_name == "query_metadata":
            dt = str(params.get("data_type", "")).upper()
            if dt == "DEM":
                return "dem_results"
            if dt == "DOM":
                return "dom_results"
            if dt == "TSP":
                return "tsp_results"
            if dt in ("GPR",):
                return "gpr_results"
            if dt == "TBM":
                return "tbm_results"
            return "dem_results"

        if tool_name == "import_dataset":
            dtype = str(params.get("dataset_type", "")).upper()
            if dtype == "DEM":
                return "dem_import"
            if dtype == "DOM":
                return "dom_import"
            if dtype == "TSP":
                return "tsp_import"
            if dtype == "TBM":
                return "tbm_import"
            return "generic_import"

        if tool_name == "interpolate_spatial":
            method = str(params.get("method", "kriging")).lower()
            return method if method in ("kriging", "idw") else "kriging"

        if tool_name == "boolean_operation":
            op = str(params.get("operation", "difference")).lower()
            return op if op in ("difference", "union") else "difference"

        if tool_name == "create_view":
            layout = str(params.get("layout", "single")).lower()
            return layout if layout in ("single", "split_h", "quad") else "single"

        return "success"

    def patch(self, tools: list):
        """上下文管理器：临时替换工具函数。"""
        return _PatchContext(self, tools)


class _PatchContext:
    def __init__(self, interceptor: MockToolInterceptor, tools: list):
        self._interceptor = interceptor
        self._tools = tools
        self._originals: dict = {}

    def __enter__(self):
        for tool in self._tools:
            name = tool.name
            self._originals[name] = tool.func if hasattr(tool, "func") else None
            mock = self._interceptor.make_mock_fn(name, self._originals[name])
            if hasattr(tool, "func"):
                tool.func = mock
        return self

    def __exit__(self, *args):
        for tool in self._tools:
            name = tool.name
            if name in self._originals and self._originals[name] is not None:
                tool.func = self._originals[name]


# ── 单 Agent 执行器 ────────────────────────────────────────────────────────────

def run_single_agent_case(
    case: dict,
    agent,           # create_react_agent 返回的 compiled graph
    tools: list,     # Agent 使用的工具列表（用于拦截）
) -> CaseResult:
    """
    执行单条测试用例（单 Agent 模式）。

    Args:
        case:    YAML 解析的用例字典
        agent:   LangGraph compiled agent graph
        tools:   Agent 工具列表

    Returns:
        CaseResult
    """
    result = CaseResult(
        case_id=case["id"],
        case_name=case["name"],
        agent=case.get("agent", ""),
        level=case.get("level", "L1"),
        prompt=case["prompt"],
        expected_tools=[s["tool"] for s in case.get("expected_tool_sequence", [])],
        expected_steps=len(case.get("expected_tool_sequence", [])) or 1,
    )

    interceptor = MockToolInterceptor(case.get("mock_responses"))

    try:
        t0 = time.perf_counter()
        with interceptor.patch(tools):
            output = agent.invoke({"messages": [{"role": "user", "content": case["prompt"]}]})
        result.latency_s = time.perf_counter() - t0

        # 收集调用记录
        result.actual_tool_calls = interceptor.records

        # 参数比对
        expected_seq = case.get("expected_tool_sequence", [])
        _fill_param_matches(result, expected_seq)

        # 终态验证
        result.reached_expected_state = _check_final_state(
            interceptor.records, case.get("expected_final_state", {})
        )
        result.final_success = result.reached_expected_state

        # Token 统计（从 LangGraph output 中提取，若有）
        _extract_token_usage(result, output)

    except Exception as e:
        result.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"

    return result


def run_multi_agent_case(
    case: dict,
    system,          # create_geo_modeling_system 返回的 compiled graph
    all_tools: dict[str, list],  # {agent_name: [tools]}
) -> CaseResult:
    """
    执行单条多智能体测试用例。

    Args:
        case:      YAML 解析的用例字典
        system:    完整的多智能体系统 graph
        all_tools: 各子 Agent 的工具列表（{agent_name: tools}）

    Returns:
        CaseResult
    """
    result = CaseResult(
        case_id=case["id"],
        case_name=case["name"],
        agent="multi_agent",
        level=case.get("level", "L2"),
        prompt=case["prompt"],
        expected_tools=[s["tool"] for s in case.get("expected_tool_sequence", [])],
        expected_steps=len(case.get("expected_tool_sequence", [])) or 1,
        expected_agents=case.get("expected_agents", []),
    )

    # 拦截所有子 Agent 工具
    all_tool_list = []
    for tools in all_tools.values():
        all_tool_list.extend(tools)

    interceptor = MockToolInterceptor(case.get("mock_responses"))

    try:
        t0 = time.perf_counter()
        with interceptor.patch(all_tool_list):
            output = system.invoke(
                {"messages": [{"role": "user", "content": case["prompt"]}]},
                config={"recursion_limit": 50},
            )
        result.latency_s = time.perf_counter() - t0

        result.actual_tool_calls = interceptor.records

        # 参数比对
        expected_seq = case.get("expected_tool_sequence", [])
        _fill_param_matches(result, expected_seq)

        # 路由信息（从消息流中提取 agent_name）
        result.routed_agents = _extract_routed_agents(output)

        # 终态验证
        result.reached_expected_state = _check_final_state(
            interceptor.records, case.get("expected_final_state", {})
        )
        result.final_success = result.reached_expected_state

        _extract_token_usage(result, output)

    except Exception as e:
        result.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"

    return result


# ── 辅助函数 ───────────────────────────────────────────────────────────────────

def _fill_param_matches(result: CaseResult, expected_seq: list[dict]):
    """将期望参数与实际工具调用按顺序配对，填充 param_match。"""
    # 建立期望工具名→期望参数的映射（处理同名工具多次调用的情况）
    expected_map: dict[str, list[dict]] = {}
    for step in expected_seq:
        name = step["tool"]
        expected_map.setdefault(name, []).append(step.get("params", {}))

    call_counters: dict[str, int] = {}
    for record in result.actual_tool_calls:
        name = record.tool_name
        idx = call_counters.get(name, 0)
        call_counters[name] = idx + 1

        candidates = expected_map.get(name, [])
        if idx < len(candidates):
            expected_params = candidates[idx]
            record.param_match = compare_tool_call(name, expected_params, record.params)


def _check_final_state(records: list[ToolCallRecord], expected_state: dict) -> bool:
    """
    终态验证：检查最后一条工具调用是否满足期望状态。
    仅验证 expected_state 中指定的字段。
    """
    if not expected_state:
        return bool(records)  # 有任何调用就算通过

    if not records:
        return False

    last = records[-1].response
    if expected_state.get("success") is not None:
        if last.get("success") != expected_state["success"]:
            return False

    contains_field = expected_state.get("contains_field")
    if contains_field:
        if last.get(contains_field) is None and last.get("data") is None:
            return False

    return True


def _extract_routed_agents(output: dict) -> list[str]:
    """从 LangGraph 输出消息中提取子 Agent 名称。"""
    agents = []
    messages = output.get("messages", [])
    for msg in messages:
        # LangGraph Supervisor 输出中，子 Agent 的消息有 name 属性
        name = getattr(msg, "name", None)
        if name and name not in agents:
            agents.append(name)
    return agents


def _extract_token_usage(result: CaseResult, output: dict):
    """尝试从 LangGraph output 中提取 token 使用量。"""
    try:
        messages = output.get("messages", [])
        for msg in reversed(messages):
            usage = getattr(msg, "usage_metadata", None)
            if usage:
                result.input_tokens = usage.get("input_tokens", 0)
                result.output_tokens = usage.get("output_tokens", 0)
                break
    except Exception:
        pass
