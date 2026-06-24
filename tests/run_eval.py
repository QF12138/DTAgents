"""
DTAgents 评测框架 CLI 入口

用法示例：
    # 评测单个 agent（Mock 模式）
    python tests/run_eval.py --provider qwen --model qwen2.5:7b --agent initialization

    # 评测特定难度
    python tests/run_eval.py --provider deepseek --level L1,L2

    # 评测所有 agent
    python tests/run_eval.py --provider anthropic

    # 多智能体评测
    python tests/run_eval.py --provider anthropic --agent multi_agent

    # 生成 Markdown 报告
    python tests/run_eval.py --provider qwen --output report.md

    # 跨 provider 对比（串行，需要多个有效 API Key）
    python tests/run_eval.py --compare --providers anthropic,qwen,deepseek
"""
from __future__ import annotations

import argparse
import sys
import os
import time
from pathlib import Path

# 将项目根目录加入 sys.path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from tests.eval_framework.metrics import AggregatedMetrics, CaseResult
from tests.eval_framework.reporter import print_summary, to_json, to_markdown
from tests.eval_framework.runner import load_cases_for_agent, run_single_agent_case, run_multi_agent_case


# ── Agent 名称到模块的映射 ─────────────────────────────────────────────────────

AGENT_MAP = {
    "initialization": "agents.initialization",
    "modeling":       "agents.modeling",
    "visualization":  "agents.visualization",
}

AGENT_CLASS_MAP = {
    "initialization": "create_initialization_agent",
    "modeling":       "create_modeling_agent",
    "visualization":  "create_visualization_agent",
}

AGENT_TOOLS_MAP = {
    "initialization": "tools.initialization",
    "modeling":       "tools.modeling",
    "visualization":  "tools.visualization",
}


def _create_llm(provider: str, model: str | None, api_key: str | None,
                base_url: str | None):
    from llm_factory import create_llm
    from config import LLM_MAX_TOKENS, LLM_TEMPERATURE, LLM_DEBUG
    return create_llm(
        provider=provider,
        model=model or None,
        api_key=api_key or None,
        base_url=base_url or None,
        max_tokens=LLM_MAX_TOKENS,
        temperature=LLM_TEMPERATURE,
        reasoning=False,
        debug=LLM_DEBUG,
    )


def _warmup_llm(llm, provider: str, agent_name: str = "initialization"):
    """
    诊断预热：分三层计时，确认首次调用慢在哪个层面。

    Layer 1 - httpx 连接层：裸 LLM 调用（无 Agent、无工具）
    Layer 2 - Pydantic Schema 编译：工具 schema 首次序列化
    Layer 3 - LangGraph 图执行层：首次 agent.invoke() 编译开销
    """
    import time
    import importlib

    print(f"\n[预热诊断] provider={provider}")

    # ── Layer 1：httpx 连接池 + 模型首次推理 ──────────────────────────────────
    t = time.perf_counter()
    try:
        llm.invoke("hi")
    except Exception as e:
        print(f"  Layer 1 (裸LLM首次): ERROR {e}")
    else:
        d1 = time.perf_counter() - t
        print(f"  Layer 1 (裸LLM首次): {d1:.3f}s")

    t = time.perf_counter()
    try:
        llm.invoke("hi")
    except Exception as e:
        print(f"  Layer 1 (裸LLM第二次): ERROR {e}")
    else:
        d1b = time.perf_counter() - t
        diff = d1 - d1b
        print(f"  Layer 1 (裸LLM第二次): {d1b:.3f}s  ← 差值 {diff:+.3f}s"
              f"{'  ★ httpx/连接层开销' if diff > 0.5 else ''}")

    # ── Layer 2：Pydantic v2 工具 Schema 首次编译 ─────────────────────────────
    tools = _get_agent_tools(agent_name)
    t = time.perf_counter()
    for tool in tools:
        try:
            _ = tool.args_schema.model_json_schema()
        except Exception:
            pass
    d2 = time.perf_counter() - t
    print(f"  Layer 2 (工具Schema编译, {len(tools)}个工具): {d2:.3f}s"
          f"{'  ★ Pydantic编译开销' if d2 > 0.3 else ''}")

    # ── Layer 3：LangGraph 图首次执行编译 ─────────────────────────────────────
    try:
        mod = importlib.import_module(AGENT_MAP[agent_name])
        create_fn = getattr(mod, AGENT_CLASS_MAP[agent_name])
        agent = create_fn(llm)
        t = time.perf_counter()
        try:
            agent.invoke(
                {"messages": [{"role": "user", "content": "hi"}]},
                config={"recursion_limit": 2},
            )
        except Exception:
            pass
        d3a = time.perf_counter() - t
        print(f"  Layer 3 (Agent图首次invoke): {d3a:.3f}s")

        t = time.perf_counter()
        try:
            agent.invoke(
                {"messages": [{"role": "user", "content": "hi"}]},
                config={"recursion_limit": 2},
            )
        except Exception:
            pass
        d3b = time.perf_counter() - t
        diff3 = d3a - d3b
        print(f"  Layer 3 (Agent图第二次invoke): {d3b:.3f}s  ← 差值 {diff3:+.3f}s"
              f"{'  ★ LangGraph图编译开销' if diff3 > 0.5 else ''}")
    except Exception as e:
        print(f"  Layer 3: SKIP ({e})")

    print()


def _get_agent_tools(agent_name: str) -> list:
    """动态导入指定 Agent 的工具列表。"""
    tool_module_name = AGENT_TOOLS_MAP.get(agent_name, "")
    if not tool_module_name:
        return []
    try:
        import importlib
        module = importlib.import_module(tool_module_name)
        # 约定：tools 模块导出 __all__ 或所有 tool 函数
        all_names = getattr(module, "__all__", [])
        tools = [getattr(module, name) for name in all_names
                 if hasattr(getattr(module, name), "name")]
        return tools
    except Exception as e:
        print(f"[WARN] 无法导入工具模块 {tool_module_name}: {e}")
        return []


def run_agent_eval(
    agent_name: str,
    llm,
    level_filter: list[str] | None,
    cases_dir: Path,
) -> list[CaseResult]:
    """运行单个 Agent 的全部测试用例。"""
    import importlib

    # 加载用例
    cases = load_cases_for_agent(agent_name, level_filter, cases_dir)
    if not cases:
        print(f"[WARN] 未找到 agent={agent_name} 的测试用例，跳过")
        return []

    # 创建 Agent
    module_name = AGENT_MAP[agent_name]
    fn_name = AGENT_CLASS_MAP[agent_name]
    try:
        module = importlib.import_module(module_name)
        create_fn = getattr(module, fn_name)
        agent = create_fn(llm)
    except Exception as e:
        print(f"[ERROR] 创建 Agent {agent_name} 失败: {e}")
        return []

    # 获取工具列表
    tools = _get_agent_tools(agent_name)

    results = []
    for case in cases:
        print(f"  [{case['id']}] {case['name']} ... ", end="", flush=True)
        result = run_single_agent_case(case, agent, tools)
        status = "✓" if result.final_success else "✗"
        if result.error:
            status = "E"
        print(f"{status} (TSA={result.tsa:.0%} PA={result.pa:.0%} "
              f"STC={result.stc:.0%} {result.latency_s:.1f}s)")
        results.append(result)

    return results


def run_multi_agent_eval(
    llm,
    level_filter: list[str] | None,
    cases_dir: Path,
) -> list[CaseResult]:
    """运行多智能体测试用例。"""
    from agents.planner import create_geo_modeling_system
    from agents.initialization import create_initialization_agent
    from agents.modeling import create_modeling_agent
    from agents.visualization import create_visualization_agent

    cases = load_cases_for_agent("multi_agent", level_filter, cases_dir)
    if not cases:
        print("[WARN] 未找到 multi_agent 测试用例，跳过")
        return []

    system = create_geo_modeling_system(llm)

    # 收集各子 Agent 工具（用于拦截）
    all_tools = {
        "initialization": _get_agent_tools("initialization"),
        "modeling":       _get_agent_tools("modeling"),
        "visualization":  _get_agent_tools("visualization"),
    }

    results = []
    for case in cases:
        print(f"  [{case['id']}] {case['name']} ... ", end="", flush=True)
        result = run_multi_agent_case(case, system, all_tools)
        status = "✓" if result.final_success else "✗"
        if result.error:
            status = "E"
        print(f"{status} (E2E={result.tsr:.0%} PRA={result.pra:.0%} "
              f"{result.latency_s:.1f}s)")
        results.append(result)

    return results


def main():
    parser = argparse.ArgumentParser(
        description="DTAgents 多智能体评测框架",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    # LLM 配置
    parser.add_argument("--provider", default="anthropic",
                        choices=["anthropic", "openai", "deepseek", "qwen", "gemini", "ollama"],
                        help="LLM provider（默认: anthropic）")
    parser.add_argument("--model", default=None,
                        help="模型名称（None 时使用 provider 默认）")
    parser.add_argument("--api-key", default=None, help="API Key（覆盖环境变量）")
    parser.add_argument("--base-url", default=None, help="服务地址（主要用于 Ollama）")

    # 评测范围
    parser.add_argument("--agent", default=None,
                        help="评测的 Agent（initialization/modeling/visualization/multi_agent/all）")
    parser.add_argument("--level", default=None,
                        help="难度过滤，逗号分隔（如 L1,L2）")

    # 输出
    parser.add_argument("--output", default=None,
                        help="输出文件路径（.json 或 .md）")
    parser.add_argument("--json", action="store_true",
                        help="同时输出 JSON 格式")

    # 对比模式
    parser.add_argument("--compare", action="store_true",
                        help="多 provider 对比模式（配合 --providers 使用）")
    parser.add_argument("--providers", default=None,
                        help="对比的 provider 列表，逗号分隔（如 anthropic,qwen）")

    # 诊断
    parser.add_argument("--warmup", action="store_true",
                        help="运行前执行三层预热诊断（httpx / Pydantic / LangGraph）")

    args = parser.parse_args()

    # 确定测试用例目录
    cases_dir = ROOT / "tests" / "test_cases"

    # 确定要评测的 agent
    agent_arg = args.agent or "all"
    if agent_arg == "all":
        target_agents = list(AGENT_MAP.keys()) + ["multi_agent"]
    elif "," in agent_arg:
        target_agents = [a.strip() for a in agent_arg.split(",")]
    else:
        target_agents = [agent_arg]

    # 难度过滤
    level_filter = None
    if args.level:
        level_filter = [l.strip().upper() for l in args.level.split(",")]

    # ── 单 Provider 模式 ──────────────────────────────────────────────────────
    if not args.compare:
        print(f"\n{'='*60}")
        print(f"  Provider: {args.provider}  Model: {args.model or '(default)'}")
        print(f"  Agents: {target_agents}  Level: {level_filter or 'ALL'}")
        print(f"{'='*60}\n")

        try:
            llm = _create_llm(args.provider, args.model, args.api_key, args.base_url)
        except Exception as e:
            print(f"[ERROR] 创建 LLM 失败: {e}")
            sys.exit(1)

        if args.warmup:
            _warmup_llm(llm, args.provider)

        all_results: list[CaseResult] = []

        for agent_name in target_agents:
            print(f"\n--- {agent_name.upper()} ---")
            if agent_name == "multi_agent":
                results = run_multi_agent_eval(llm, level_filter, cases_dir)
            elif agent_name in AGENT_MAP:
                results = run_agent_eval(agent_name, llm, level_filter, cases_dir)
            else:
                print(f"[WARN] 未知 agent: {agent_name}，跳过")
                continue
            all_results.extend(results)

        # 聚合指标
        aggregated = [
            AggregatedMetrics.from_cases(
                [c for c in all_results if c.agent == a or
                 (a == "multi_agent" and c.agent == "multi_agent")],
                label=a,
                provider=args.provider,
                model=args.model or "(default)",
                agent_filter=a,
            )
            for a in target_agents
        ]
        aggregated = [m for m in aggregated if m.case_count > 0]

        # 汇总
        total_agg = AggregatedMetrics.from_cases(
            all_results, label="TOTAL",
            provider=args.provider,
            model=args.model or "(default)",
            agent_filter="ALL",
        )
        if total_agg.case_count > 0:
            aggregated.append(total_agg)

        print_summary(aggregated)

        # 输出文件
        if args.output:
            out_path = Path(args.output)
            if out_path.suffix == ".json" or args.json:
                to_json(aggregated, all_results, out_path)
                print(f"JSON 报告已写入: {out_path}")
            else:
                to_markdown(aggregated, all_results, out_path)
                print(f"Markdown 报告已写入: {out_path}")

        if args.json and args.output and not args.output.endswith(".json"):
            json_path = Path(args.output).with_suffix(".json")
            to_json(aggregated, all_results, json_path)
            print(f"JSON 报告已写入: {json_path}")

    # ── 多 Provider 对比模式 ────────────────────────────────────────────────────
    else:
        providers = [p.strip() for p in (args.providers or args.provider).split(",")]
        print(f"\n{'='*60}")
        print(f"  对比模式: {providers}")
        print(f"  Agents: {target_agents}  Level: {level_filter or 'ALL'}")
        print(f"{'='*60}\n")

        all_aggregated: list[AggregatedMetrics] = []
        all_raw_cases: list[CaseResult] = []

        for provider in providers:
            print(f"\n>>> Provider: {provider}")
            try:
                llm = _create_llm(provider, args.model, args.api_key, args.base_url)
            except Exception as e:
                print(f"[ERROR] 创建 LLM ({provider}) 失败: {e}，跳过")
                continue

            if args.warmup:
                _warmup_llm(llm, provider)

            provider_results: list[CaseResult] = []
            for agent_name in target_agents:
                print(f"  --- {agent_name.upper()} ---")
                if agent_name == "multi_agent":
                    results = run_multi_agent_eval(llm, level_filter, cases_dir)
                elif agent_name in AGENT_MAP:
                    results = run_agent_eval(agent_name, llm, level_filter, cases_dir)
                else:
                    continue
                provider_results.extend(results)

            all_raw_cases.extend(provider_results)
            agg = AggregatedMetrics.from_cases(
                provider_results,
                label=f"{provider}",
                provider=provider,
                model=args.model or "(default)",
                agent_filter="ALL",
            )
            all_aggregated.append(agg)

        print_summary(all_aggregated)

        if args.output:
            out_path = Path(args.output)
            if out_path.suffix == ".json":
                to_json(all_aggregated, all_raw_cases, out_path)
            else:
                to_markdown(all_aggregated, all_raw_cases, out_path,
                            title="DTAgents 多模型对比评测报告")
            print(f"报告已写入: {args.output}")


if __name__ == "__main__":
    main()
