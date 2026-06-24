"""
评测结果报告生成器

支持两种输出格式：
  1. JSON：详细原始数据（用于程序消费）
  2. Markdown 表格：可读的对比报告（用于人工分析）
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from tests.eval_framework.metrics import AggregatedMetrics, CaseResult


# ── JSON 报告 ──────────────────────────────────────────────────────────────────

def to_json(
    aggregated: list[AggregatedMetrics],
    raw_cases: list[CaseResult] | None = None,
    output_path: str | Path | None = None,
) -> str:
    """生成 JSON 格式报告。"""
    report = {
        "generated_at": datetime.now().isoformat(),
        "summary": [m.as_dict() for m in aggregated],
    }

    if raw_cases:
        report["details"] = []
        for c in raw_cases:
            entry = {
                "id": c.case_id,
                "name": c.case_name,
                "agent": c.agent,
                "level": c.level,
                "TSA": round(c.tsa, 4),
                "PA": round(c.pa, 4),
                "TCF1": round(c.tcf1, 4),
                "TSR": c.tsr,
                "STC": round(c.stc, 4),
                "HAL": round(c.hal, 4),
                "PRA": round(c.pra, 4),
                "latency_s": round(c.latency_s, 3),
                "total_tokens": c.total_tokens,
                "expected_tools": c.expected_tools,
                "actual_tools": c.actual_tools,
                "success": c.final_success,
                "error": c.error,
            }
            # 参数比对明细
            entry["param_details"] = []
            for r in c.actual_tool_calls:
                if r.param_match:
                    entry["param_details"].append({
                        "tool": r.tool_name,
                        "PA": round(r.param_match.param_accuracy, 4),
                        "HAL": round(r.param_match.hallucination_rate, 4),
                        "matched": r.param_match.matched_fields,
                        "missing": r.param_match.missing_fields,
                        "wrong": r.param_match.wrong_value_fields,
                        "hallucinated": r.param_match.hallucinated_fields,
                    })
            report["details"].append(entry)

    json_str = json.dumps(report, ensure_ascii=False, indent=2)
    if output_path:
        Path(output_path).write_text(json_str, encoding="utf-8")
    return json_str


# ── Markdown 报告 ──────────────────────────────────────────────────────────────

def _fmt(val: float, pct: bool = True) -> str:
    if pct:
        return f"{val:.1%}"
    return f"{val:.2f}"


def to_markdown(
    aggregated: list[AggregatedMetrics],
    raw_cases: list[CaseResult] | None = None,
    output_path: str | Path | None = None,
    title: str = "DTAgents 评测报告",
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [f"# {title}", f"> 生成时间：{now}", ""]

    # ── 汇总表格 ──────────────────────────────────────────────────────────────
    lines.append("## 汇总指标")
    lines.append("")
    lines.append("| Provider | Model | Agent | 用例数 | TSA | PA | TCF1 | TSR | STC | HAL | Tokens | Latency |")
    lines.append("|----------|-------|-------|--------|-----|-----|------|-----|-----|-----|--------|---------|")

    for m in aggregated:
        provider = m.provider or "-"
        model = m.model or "-"
        agent = m.agent_filter or "ALL"
        lines.append(
            f"| {provider} | {model} | {agent} | {m.case_count} "
            f"| {_fmt(m.avg_tsa)} | {_fmt(m.avg_pa)} | {_fmt(m.avg_tcf1)} "
            f"| {_fmt(m.avg_tsr)} | {_fmt(m.avg_stc)} | {_fmt(m.avg_hal)} "
            f"| {int(m.avg_total_tokens)} | {m.avg_latency_s:.1f}s |"
        )

    lines.append("")

    # ── 按难度分级汇总 ─────────────────────────────────────────────────────────
    if raw_cases:
        lines.append("## 按难度分级")
        lines.append("")
        from collections import defaultdict
        by_level: dict[str, list[CaseResult]] = defaultdict(list)
        for c in raw_cases:
            by_level[c.level].append(c)

        lines.append("| 级别 | 用例数 | TSA | PA | TSR | STC |")
        lines.append("|------|--------|-----|-----|-----|-----|")
        for level in sorted(by_level.keys()):
            group = by_level[level]
            agg = AggregatedMetrics.from_cases(group, label=level)
            lines.append(
                f"| {level} | {len(group)} "
                f"| {_fmt(agg.avg_tsa)} | {_fmt(agg.avg_pa)} "
                f"| {_fmt(agg.avg_tsr)} | {_fmt(agg.avg_stc)} |"
            )
        lines.append("")

        # ── 失败用例明细 ──────────────────────────────────────────────────────
        failed = [c for c in raw_cases if not c.final_success]
        if failed:
            lines.append("## 失败用例明细")
            lines.append("")
            lines.append("| ID | 名称 | Agent | Level | 期望工具 | 实际工具 | 错误 |")
            lines.append("|----|------|-------|-------|----------|----------|------|")
            for c in failed:
                exp = ", ".join(c.expected_tools) or "-"
                act = ", ".join(c.actual_tools) or "-"
                err = (c.error or "")[:60].replace("\n", " ") if c.error else "-"
                lines.append(f"| {c.case_id} | {c.case_name} | {c.agent} "
                             f"| {c.level} | {exp} | {act} | {err} |")
            lines.append("")

        # ── 参数幻觉问题 ──────────────────────────────────────────────────────
        hal_cases = [c for c in raw_cases if c.hal > 0]
        if hal_cases:
            lines.append("## 参数幻觉问题（HAL > 0）")
            lines.append("")
            lines.append("| ID | Agent | HAL | 幻觉字段 |")
            lines.append("|----|-------|-----|----------|")
            for c in hal_cases:
                hal_fields = []
                for r in c.actual_tool_calls:
                    if r.param_match and r.param_match.hallucinated_fields:
                        hal_fields.extend(
                            f"{r.tool_name}.{f}" for f in r.param_match.hallucinated_fields
                        )
                lines.append(f"| {c.case_id} | {c.agent} | {_fmt(c.hal)} "
                             f"| {', '.join(hal_fields)} |")
            lines.append("")

    md = "\n".join(lines)
    if output_path:
        Path(output_path).write_text(md, encoding="utf-8")
    return md


# ── 控制台快速打印 ─────────────────────────────────────────────────────────────

def print_summary(aggregated: list[AggregatedMetrics]):
    """在控制台输出简洁的评测摘要。"""
    print("\n" + "=" * 80)
    print(f"{'Provider':<12} {'Model':<20} {'Agent':<20} {'TSA':>6} {'PA':>6} "
          f"{'TSR':>6} {'STC':>6} {'HAL':>6} {'Tok':>6} {'Lat':>6}")
    print("-" * 80)
    for m in aggregated:
        print(
            f"{(m.provider or '-'):<12} {(m.model or '-'):<20} "
            f"{(m.agent_filter or 'ALL'):<20} "
            f"{m.avg_tsa:>6.1%} {m.avg_pa:>6.1%} "
            f"{m.avg_tsr:>6.1%} {m.avg_stc:>6.1%} "
            f"{m.avg_hal:>6.1%} {int(m.avg_total_tokens):>6} "
            f"{m.avg_latency_s:>5.1f}s"
        )
    print("=" * 80 + "\n")
