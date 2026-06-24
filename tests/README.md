# DTAgents 评测框架

本文档描述针对 DTAgents 多智能体地质建模系统的评测框架设计与使用方法。

---

## 一、背景与目标

当前系统支持多个 LLM provider（Anthropic、OpenAI、DeepSeek、Qwen、Gemini、Ollama），各模型在工具调用的准确率和效率方面差异显著。本框架旨在：

1. **量化对比**不同 LLM 在本系统工具链上的表现
2. **评估单智能体**的工具选择、参数填充、多步推理能力
3. **评估多智能体协同**的 Planner 路由准确性和整体效率
4. **支持"分层模型"策略**选型（Planner 用大模型 vs 子 Agent 用小模型）

---

## 二、参考基准文献综述

| Benchmark | 来源 | 核心贡献 | 本框架借鉴点 |
|-----------|------|---------|------------|
| **BFCL v4** | Berkeley | AST 参数结构比对；多轮评估 | AST 参数验证；多轮成功率 |
| **ToolBench** | SambaNova | Act.EM / Avg.F1；多步 API 序列 | 工具选择精确匹配；F1 分数 |
| **AgentBench** | THUDM / ICLR'24 | 8 环境；长期推理；决策质量 | 任务完成率；指令跟随 |
| **MultiAgentBench** | ACL'25 | 协作/竞争；协调效率；通信开销 | Planner 路由准确率；通信开销 |
| **DeepEval / RAGAS** | 开源框架 | ToolCallAccuracy；ParameterAccuracy | 幻觉参数检测；工具正确性 |

### 主要评测方法对比

**BFCL（Berkeley Function Calling Leaderboard）**
- 测试内容：串行/并行工具调用、多轮交互、工具选择时机
- 评分方法：**AST 参数结构比对**（无需执行真实函数，解析参数 JSON 结构与期望 schema 比对）
- 关键发现：顶级模型在单轮问题表现优异，但多轮长上下文和"何时不调用工具"仍是薄弱点

**ToolBench**
- 测试内容：16,464 个真实 RESTful API，多步骤 API 调用序列
- 指标：Act.EM（动作精确匹配）、Avg.F1（工具调用平均 F1）

**AgentBench**
- 测试内容：操作系统、数据库、游戏、家务等 8 个环境
- 关键发现：顶级商业 LLM 与开源 ≤70B 模型存在显著差距，主要障碍是长期推理和指令跟随

**MultiAgentBench**
- 测试内容：智能体协作拓扑（星形、链式、树形、图形）
- 指标：成功率（SR）、协调效率、通信开销、进度率（Progress Rate）

---

## 三、评价指标体系

### 3.1 单智能体指标

| 指标 | 缩写 | 定义 | 计算方式 |
|------|------|------|---------|
| 工具选择准确率 | **TSA** | 期望工具被正确调用的比例 | `命中期望工具数 / 期望工具总数` |
| 参数精确率 | **PA** | 参数字段完全正确的比例 | AST 结构比对（字段名+类型+值） |
| 工具调用 F1 | **TCF1** | 工具选择的综合 Precision×Recall | `2×P×R/(P+R)`，多余调用扣 P，遗漏扣 R |
| 任务完成率 | **TSR** | 成功达到期望终态的比例 | 检查最终工具返回 `success=True` + 输出合法 |
| 步骤效率 | **STC** | 期望最少步骤数 / 实际步骤数 | 越接近 1.0 越好（>1 意味着少走了步骤） |
| 幻觉参数率 | **HAL** | 调用了 schema 中不存在参数的比例 | `幻觉字段数 / 实际字段数` |

**AST 参数比对规则**（参考 BFCL）：
- `str`：大小写不敏感
- `int / float`：互兼容，比较数值（误差 < 1e-9）
- `list`：逐元素比对（顺序敏感）
- `dict`：递归比对
- 期望参数为子集：实际参数可包含额外可选字段，但会标记为幻觉参数

### 3.2 多智能体指标

| 指标 | 缩写 | 定义 |
|------|------|------|
| Planner 路由准确率 | **PRA** | 任务被路由到正确子 Agent 的比例 |
| 子任务完成率 | **SCR** | 多步工作流中各子任务均完成的比例 |
| 通信开销 | **CO** | Agent 间消息总轮次 / 完成的子任务数（越小越好） |
| 端到端成功率 | **E2E** | 完整流程从用户输入到最终输出成功的比例 |
| 端到端延迟 | **E2E-L** | 完整流程的总耗时（秒） |
| Token 消耗 | **TOK** | 完成任务的总 token 数（input + output） |

### 3.3 评分方法

| 方法 | 适用场景 | 优点 | 局限 |
|------|---------|------|------|
| **AST 比对** | 工具参数验证 | 快速、确定性、无需执行 | 不捕获运行时语义错误 |
| **执行验证** | 终态判断 | 语义正确性 | 依赖 Mock 或真实环境 |
| **终态验证** | 多步骤流程 | 允许替代路径 | 不验证中间步骤 |

---

## 四、测试用例设计

### 4.1 难度分级

| 级别 | 描述 | 工具调用数 | 典型特征 |
|------|------|-----------|---------|
| **L1** | 单步直接调用 | 1 | 参数明确，无歧义 |
| **L2** | 条件判断 + 两步 | 2 | 需根据第一步结果决定第二步参数 |
| **L3** | 多步顺序 + 结果依赖 | 3～4 | 跨工具数据传递，Entity ID 引用 |
| **L4** | 边界/错误处理 | ≥2（含失败分支） | 空结果停止、超阈值暂停、歧义输入 |

### 4.2 用例统计

| 智能体 | 用例数 | L1 | L2 | L3 | L4 |
|-------|--------|----|----|----|----|
| InitializationAgent | 16 | 4 | 4 | 4 | 4 |
| PreprocessingAgent | 12 | 3 | 4 | 3 | 2 |
| ModelingAgent | 12 | 3 | 4 | 3 | 2 |
| VisualizationAgent | 8 | 3 | 3 | 2 | — |
| 多智能体协同 | 12 | 3 | 4 | 3 | 2 |
| **合计** | **60** | **16** | **19** | **15** | **10** |

### 4.3 用例类型覆盖

**PreprocessingAgent（12 条）**
- L1：CRS坐标系转换、里程转三维空间坐标、工程尺度区域裁剪（含里程区间）
- L2：里程转换→洞内裁剪、洞内裁剪→空间采样（边界ID链传）、双数据连续CRS转换、CRS转换→全线裁剪
- L3：AHD钻孔完整三步流水线、DEM/DOM双转换后裁剪、混合地表+洞内流程
- L4：未指定覆盖范围时跳过裁剪、非钻孔数据（DEM）不执行空间采样

**InitializationAgent（16 条）**
- L1：查工程列表、查工点、按工程查 DEM、按里程查工点
- L2：两步顺序（工程→TSP/GPR/DRL/多类型）
- L3：三步完整流程（查询→检索→导入 DEM/TSP/DOM/TBM）
- L4：不存在工程、超阈值确认、里程格式识别、歧义输入处理

**ModelingAgent（12 条）**
- L1：DEM 三角剖分、等值面提取、DOM 纹理贴图
- L2：克里金插值→等值面、IDW 参数填充、地质体建模+验证、布尔差运算
- L3：随机森林分类→等值面、DEM+DOM 完整建模、插值→分类→提取
- L4：克里金高级参数（变程/块金/基台）、地质体倾角走向参数

**VisualizationAgent（8 条）**
- L1：线框模式、俯视图、实体聚焦
- L2：Z 轴切片、分割视图+等轴侧视、viridis 色图透明度
- L3：多组实体差异化配置、四分视图四方向

**多智能体协同（12 条）**
- 简单路由：三类任务分别路由至正确子 Agent
- 两阶段：Init→Modeling、Init→Visualization、Init→Modeling→Visualization
- 三阶段：完整 DEM+DOM 建模展示、钻孔克里金建模、里程段超前预报
- 错误恢复：工程不存在时停止、超阈值时不强行继续

### 4.4 用例文件格式（YAML）

```yaml
id: T-I-05
name: "L2-两步顺序-工程名查TSP数据"
agent: InitializationAgent
level: L2
prompt: "请查询隧道工程A项目下的TSP超前地质预报数据"

# 期望工具调用序列（顺序+参数子集）
expected_tool_sequence:
  - tool: query_hierarchy
    params:
      level: project
  - tool: query_metadata
    params:
      data_type: "TSP"

# 终态验证
expected_final_state:
  success: true
  contains_field: data

# Mock 工具返回值（每种工具指定一个固定返回）
mock_responses:
  query_hierarchy:
    success: true
    data:
      - project_id: "P001"
        name: "隧道工程A"
    message: "查询到 1 个工程"
    metadata: {count: 1}
  query_metadata:
    success: true
    data:
      - dataset_id: "D010"
        name: "tsp_dk5.csv"
        data_type: "TSP"
        file_path: "data/raw/tsp_dk5.csv"
    message: "查询到 1 个数据集"
    metadata: {count: 1}
```

---

## 五、工程结构

```
tests/
├── README.md                        # 本文档
├── run_eval.py                      # CLI 评测入口
├── eval_framework/
│   ├── __init__.py
│   ├── runner.py                    # 测试执行器（单 Agent / 多 Agent）
│   ├── scorer.py                    # AST 参数比对评分器
│   ├── metrics.py                   # 指标计算（TSA、PA、TCF1、TSR、STC、HAL 等）
│   └── reporter.py                  # 报告生成（JSON + Markdown）
├── fixtures/
│   ├── __init__.py
│   └── mock_tools.py                # 所有工具的 Mock 返回值库
└── test_cases/
    ├── initialization/              # T-I-01 ~ T-I-16（16 条）
    ├── preprocessing/               # T-P-01 ~ T-P-12（12 条）
    ├── modeling/                    # T-M-01 ~ T-M-12（12 条）
    ├── visualization/               # T-V-01 ~ T-V-08（8 条）
    └── multi_agent/                 # T-MA-01 ~ T-MA-12（12 条）
```

---

## 六、使用方法

### 6.1 基本评测（单 Provider）

```bash
# 评测所有 Agent（使用默认 provider: anthropic）
python tests/run_eval.py

# 指定 Provider 和 Model
python tests/run_eval.py --provider qwen --model qwen2.5:7b

# 本地 Ollama
python tests/run_eval.py --provider ollama --model qwen2.5:7b --base-url http://localhost:11434

# 指定 API Key（覆盖环境变量）
python tests/run_eval.py --provider deepseek --api-key sk-xxxx
```

### 6.2 按 Agent 和难度过滤

```bash
# 只测 InitializationAgent
python tests/run_eval.py --provider qwen --agent initialization

# 只测 L1 和 L2 难度
python tests/run_eval.py --provider deepseek --level L1,L2

# 只测多智能体协同
python tests/run_eval.py --provider anthropic --agent multi_agent

# 组合过滤：InitializationAgent 的 L3、L4 用例
python tests/run_eval.py --provider qwen --agent initialization --level L3,L4
```

### 6.3 输出报告

```bash
# 输出 Markdown 报告
python tests/run_eval.py --provider anthropic --output report.md

# 输出 JSON 报告
python tests/run_eval.py --provider qwen --output report.json

# 同时输出两种格式
python tests/run_eval.py --provider qwen --output report.md --json
```

### 6.4 多 Provider 对比评测

```bash
# 对比三个 provider（串行运行，需要对应 API Key）
python tests/run_eval.py --compare --providers anthropic,qwen,deepseek --output compare.md

# 对比本地 Ollama 不同模型（需分两次运行，对比报告手工合并）
python tests/run_eval.py --provider ollama --model qwen2.5:7b --output ollama_7b.md
python tests/run_eval.py --provider ollama --model qwen2.5:32b --output ollama_32b.md
```

### 6.5 期望输出格式

控制台输出示例：

```
============================================================
  Provider: qwen  Model: qwen2.5:7b
  Agents: ['initialization', 'modeling', 'visualization', 'multi_agent']  Level: ALL
============================================================

--- INITIALIZATION ---
  [T-I-01] L1-查询所有工程列表 ... ✓ (TSA=100% PA=100% STC=100% 3.2s)
  [T-I-05] L2-两步顺序-工程名查TSP数据 ... ✓ (TSA=100% PA=85% STC=100% 5.1s)
  [T-I-14] L4-错误处理-查询结果超过确认阈值 ... ✗ (TSA=100% PA=90% STC=50% 4.8s)
  ...

================================================================================
Provider      Model                Agent                TSA    PA   TSR   STC   HAL    Tok   Lat
--------------------------------------------------------------------------------
qwen          qwen2.5:7b           initialization      87.5% 82.3% 81.3% 78.9%  3.2%   1820  4.2s
qwen          qwen2.5:7b           modeling            83.3% 78.1% 75.0% 81.2%  4.1%   2100  5.8s
qwen          qwen2.5:7b           visualization       91.7% 88.5% 87.5% 85.3%  1.8%   1540  3.1s
qwen          qwen2.5:7b           multi_agent         75.0% 74.2% 66.7% 72.4%  5.3%   3200  12.4s
qwen          qwen2.5:7b           ALL                 84.4% 81.0% 78.1% 79.5%  3.6%   2165  6.4s
================================================================================
```

Markdown 报告示例：

| Provider | Model | Agent | 用例数 | TSA | PA | TCF1 | TSR | STC | HAL | Tokens | Latency |
|----------|-------|-------|--------|-----|-----|------|-----|-----|-----|--------|---------|
| anthropic | claude-opus-4-6 | ALL | 48 | 96.2% | 91.4% | 94.8% | 93.8% | 85.3% | 1.2% | 2400 | 12.1s |
| qwen | qwen2.5:7b | ALL | 48 | 84.4% | 81.0% | 82.9% | 78.1% | 79.5% | 3.6% | 1820 | 4.2s |
| ollama | qwen2.5:32b | ALL | 48 | 91.7% | 86.2% | 89.1% | 88.5% | 82.7% | 2.1% | 2100 | 38.5s |

---

## 七、Mock 模式说明

评测框架默认使用 **Mock 模式**，工具调用不执行真实逻辑：

- **Mock 返回值**：定义在 `tests/fixtures/mock_tools.py` 的 `MOCK_DB` 字典中
- **场景选择**：`runner.py` 根据工具调用参数自动选择合适的 Mock scenario（如 `level='project'` 对应 `project_list`）
- **用例级覆盖**：YAML 中的 `mock_responses` 字段优先级最高，可为特定用例定制返回值

这样设计的好处：
- 评测**只测 LLM 推理能力**（工具选择 + 参数填充），不依赖数据库/文件系统
- 测试**快速、可重复**，结果确定性强
- **零环境依赖**，在任何机器上均可运行

---

## 八、扩展指南

### 8.1 添加新测试用例

在对应目录创建 YAML 文件，按以下格式填写：

```yaml
id: T-I-17                          # 唯一 ID
name: "L2-示例用例"                   # 描述性名称
agent: InitializationAgent           # 目标 Agent
level: L2                            # 难度级别
prompt: "用户输入的自然语言指令"

expected_tool_sequence:
  - tool: query_hierarchy            # 期望调用的工具名
    params:                          # 期望的参数子集（不含可选参数）
      level: project

expected_final_state:
  success: true                      # 期望最终工具返回成功
  contains_field: data               # 期望输出包含的字段（可选）

mock_responses:                      # 工具 Mock 返回值
  query_hierarchy:
    success: true
    data: [...]
    message: "..."
    metadata: {}
```

### 8.2 添加新工具的 Schema 字段

在 `eval_framework/scorer.py` 的 `TOOL_SCHEMA_FIELDS` 中添加：

```python
TOOL_SCHEMA_FIELDS["my_new_tool"] = {"param1", "param2", "param3"}
```

### 8.3 添加新 Mock 响应

在 `fixtures/mock_tools.py` 的 `MOCK_DB` 中添加：

```python
MOCK_DB["my_new_tool"] = {
    "success": _ok(data={"result": "..."}, message="操作成功"),
    "failure": _err("操作失败"),
}
```

---

## 九、指标解读建议

| 指标 | 建议阈值 | 低于阈值的含义 |
|------|---------|--------------|
| TSA | ≥ 0.90 | 模型经常选错工具或遗漏工具调用 |
| PA | ≥ 0.85 | 参数填充错误频繁，可能误用工具 |
| TCF1 | ≥ 0.88 | 工具调用序列整体质量不足 |
| TSR | ≥ 0.80 | 任务成功率低，不适合生产使用 |
| STC | ≥ 0.75 | 步骤冗余，影响效率和 token 成本 |
| HAL | ≤ 0.05 | 幻觉参数过多，存在不可预测行为 |
| PRA（多智能体） | ≥ 0.85 | Planner 路由频繁出错 |

**分层模型策略参考**：
- Planner（Supervisor）：建议 TSA ≥ 0.95，PRA ≥ 0.90，选用 32B+ 模型
- 子 Agent：建议 TSR ≥ 0.80，PA ≥ 0.85，7B 模型通常可满足，4B 以下风险较高
