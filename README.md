# 三维空间建模多智能体系统 (DTAgents)

基于 `langgraph_supervisor` 的多智能体后端程序，面向**线性工程**（公路、铁路、隧道等），对多源异构地质数据进行自动化处理、融合建模，输出**结构属性一体化的体素模型**。

---

## 目录

- [系统概述](#系统概述)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [智能体设计](#智能体设计)
- [工具清单](#工具清单)
- [数据库设计](#数据库设计)
- [状态设计](#状态设计)
- [接入自有库](#接入自有库)
- [扩展指南](#扩展指南)
- [配置参考](#配置参考)
- [开放问题](#开放问题)

---

## 系统概述

### 适用场景

| 维度 | 规格 |
|------|------|
| 工程类型 | 公路、铁路、地铁、市政、水利等线性工程 |
| 部署方式 | 本地单机，无需服务端 |
| 研究区规模 | 数平方公里级别 |
| 数据量 | GB 级 |
| 坐标体系 | 大地坐标（地表）+ 里程坐标（洞内）双坐标 |
| 地球物理数据 | 仅读取 + 属性提取，**不做**信号处理/反演 |

### 支持数据类型（15 类）

按定位体系分为两组：

**工程/区域类（地理坐标定位，`positioning_type='spatial'`）**

| 代码 | 名称 | 典型格式 |
|------|------|---------|
| `DEM` | 数字高程模型 | GeoTIFF |
| `DOM` | 数字正射影像 | GeoTIFF |
| `DRL` | 踏勘钻孔数据 | CSV / Excel |
| `EGM` | 工程地质图   | SHP / DXF  |
| `BIM` | 建筑信息模型 | IFC / STEP |

**洞内/里程类（里程坐标定位，`positioning_type='mileage'`）**

| 代码 | 名称 | 典型格式 |
|------|------|---------|
| `TSP` | 隧道地震波反射 | VDB / CSV |
| `TEM` | 洞内瞬变电磁 | JSON |
| `GPR` | 洞内地质雷达 | JSON |
| `AHD` | 超前水平钻 | JSON |
| `DBH` | 加深炮孔 | JSON |
| `TFR` | 掌子面观测（影像/扫描/地质编录） | JSON |
| `TBM` | 隧道掘进机 | JSON |
| `RDR` | 凿岩台车 | JSON |
| `IST` | 原位试验 | JSON |
| `EMS` | 环境监测 | JSON |

> 同时具有两种坐标的数据（如已关联里程的地表钻孔）使用 `positioning_type='both'`。

### 系统架构图

```
用户自然语言指令
        │
        ▼
┌─────────────────────────────────────────────────────────────┐
│                  Planner Agent (规划协调器)                   │
│         任务分解 · 工作流编排 · 共享状态管理 · 错误恢复        │
└──────────┬──────────┬──────────┬──────────┬─────────────────┘
           ▼          ▼          ▼          ▼
    ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
    │初始化     │ │预处理对齐 │ │地球科学建模   │ │集成可视化 │
    │Init.Agent│ │PrepAgent │ │ModelAgent│ │VizAgent  │
    └──────────┘ └──────────┘ └──────────┘ └──────────┘
           │          │          │          │
           ▼          ▼          ▼          ▼
    ┌─────────────────────────────────────────────────────────┐
    │                  DuckDB 元数据索引库                      │
    │  projects · centerlines · work_sites · alignment_segments│
    │  datasets · spatial_extents · mileage_extents            │
    │  processing_history · model_registry                     │
    └─────────────────────────────────────────────────────────┘
           │                                        │
           ▼                                        ▼
    ┌─────────────┐                       ┌──────────────────┐
    │  data/      │                       │  DTGeoStudio     │
    │  ├─ raw/    │   ← 原始输入数据       │  三维可视化面板   │
    │  ├─ processed/  ← 中间处理结果       │  (实体/相机/视图) │
    │  └─ models/ │   ← 地质模型文件       └──────────────────┘
    └─────────────┘
```

> **运行时依赖**：系统需配合 **DTGeoStudio**（`DTPyRuntime`）使用，可视化智能体通过 DTPyRuntime API 直接控制软件内置三维面板，无需导出中间文件。

### 工程层级

```
工程 (project)
  └── 中线 (centerline)         ← 里程系统的基准（正洞中线、斜井中线等）
        ├── 工点 (work_site)    ← 施工管理单元（如"旗山隧道进口段"）
        └── 设计段落 (alignment_segment)  ← 围岩级别、断面参数等
```

> **核心设计**：中线是大地坐标与里程互转的桥梁，不同中线的里程系统相互独立，不可混用。

### 标准建模流程

```
InitializationAgent       PreprocessingAgent       ModelingAgent      VisualizationAgent
       │                         │                        │                    │
  register_project          clip_to_boundary        extract_stratigraphy  set_entity_visibility
  register_centerline       filter_outliers         interpolate_spatial   set_display_mode
  register_work_site        resample                classify_lithology    set_voxel_slice
  register_dataset          voxelize                model_fault (可选)    focus_on_entity
  validate_data             normalize_attributes    boolean_operation     set_standard_view
  project_transform               │                merge_voxel_attributes capture_view (可选)
  mileage_to_coord                │                validate_model        add_scene_label
  coord_to_mileage                │                export_model
       │                          │                        │                    │
       ▼                          ▼                        ▼                    ▼
  projects/centerlines/     体素网格文件              VTK/NPZ 模型文件    DTGeoStudio 三维面板
  work_sites 表             (data/processed/)        (data/models/)      (截图保存到 data/output/)
  datasets 表
  processing_history
```

---

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

> **注意**：`tools/` 下的工具函数均为接口存根（stub），需接入自有库实现（见[接入自有库](#接入自有库)）。

### 2. 配置 API Key

```bash
# Anthropic（默认）
export ANTHROPIC_API_KEY=your_key_here

# OpenAI
export LLM_PROVIDER=openai
export OPENAI_API_KEY=your_key_here

# DeepSeek
export LLM_PROVIDER=deepseek
export DEEPSEEK_API_KEY=your_key_here

# 阿里云通义千问
export LLM_PROVIDER=qwen
export DASHSCOPE_API_KEY=your_key_here

# Google Gemini
export LLM_PROVIDER=gemini
export GOOGLE_API_KEY=your_key_here
```

### 3. 修改全局配置

编辑 `config.py`，按实际项目调整：

```python
DEFAULT_VOXEL_RESOLUTION = 5.0      # 体素分辨率（米）
DEFAULT_TARGET_CRS = "EPSG:4547"    # 目标坐标系（按项目区域修改）
DEFAULT_DEPTH_MIN = -200.0          # 建模深度下限（米）
DEFAULT_DEPTH_MAX = 0.0             # 建模深度上限（地表）
```

### 4. 启动系统

```bash
# 命令行模式（默认）
python main.py

# Chainlit 网页界面
python main.py --ui
python main.py --ui --port 8080

# 显式指定 provider / 模型
python main.py --provider anthropic --model claude-opus-4-6
python main.py --provider deepseek
python main.py --provider qwen --model qwen-max
python main.py --provider gemini --model gemini-2.0-flash

# 直接传入 API Key
python main.py --provider deepseek --api-key sk-...
```

> **注意**：系统启动时需要 `DTPyRuntime` 已正确安装并可导入，否则无法启动。

### 5. 示例指令

```
>>> 注册工程"某高速公路TJ01标"，正洞中线文件在 data/raw/centerline.dxf
>>> 注册"旗山隧道进口段"工点，里程 DK12+340 ~ DK14+200
>>> 注册 data/raw/dem.tif 为 DEM 类型数据，坐标系 EPSG:4547
>>> 注册 data/raw/tsp_dk12340.json 为 TSP 数据，关联正洞中线，起始里程 DK12+340
>>> 查询所有已验证的 GPR 数据
>>> 对旗山隧道进口段进行三维空间建模，分辨率 5 米
>>> 显示岩性模型，切换为颜色表模式，截图保存
```

---

## 项目结构

```
DTAgents/
├── main.py                          # 系统入口（命令行 / Chainlit 网页界面）
├── config.py                        # 全局配置（路径、模型、分辨率、坐标系等）
├── llm_factory.py                   # LLM 工厂（支持 Anthropic / OpenAI / DeepSeek / Qwen / Gemini）
├── chainlit_app.py                  # Chainlit 网页界面入口
├── requirements.txt                 # Python 依赖
│
├── agents/                          # 智能体定义
│   ├── __init__.py
│   ├── planner.py                   # Planner Agent（Supervisor，工作流编排）
│   ├── initialization.py            # 初始化智能体（工程层级 + 数据集管理）
│   ├── preprocessing.py             # 预处理对齐智能体
│   ├── modeling.py                  # 地球科学建模智能体
│   └── visualization.py             # 可视化智能体（控制 DTGeoStudio 三维面板）
│
├── tools/                           # 工具函数（接口存根 + 实现接入点）
│   ├── common.py                    # 公共基类：ToolOutput
│   ├── initialization/
│   │   ├── hierarchy.py             # register_project/centerline/work_site/alignment_segment
│   │   ├── register.py              # register_dataset()
│   │   ├── query.py                 # query_metadata(), query_hierarchy()
│   │   ├── readers.py               # import_dataset()
│   │   ├── transform.py             # project_transform(), mileage_to_coord(), coord_to_mileage()
│   │   └── validation.py            # validate_data()
│   ├── preprocessing/
│   │   ├── voxelize.py              # voxelize()
│   │   ├── resample.py              # resample(), clip_to_boundary()
│   │   ├── sampling.py              # spatial_sample()
│   │   ├── normalize.py             # normalize_attributes(), filter_outliers()
│   │   └── convert.py               # raster_to_vector()
│   ├── modeling/
│   │   ├── interpolation.py         # interpolate_spatial()
│   │   ├── classification.py        # classify_lithology()
│   │   ├── stratigraphy.py          # extract_stratigraphy(), model_geological_body()
│   │   ├── surface.py               # delaunay_triangulation(), extract_isosurface()
│   │   ├── boolean_ops.py           # boolean_operation()
│   │   ├── validation.py            # validate_model()
│   │   └── export.py                # export_model()（导出 VTK/NPZ/HDF5，注册到数据库）
│   └── visualization/               # 直接控制 DTGeoStudio 三维面板（通过 DTPyRuntime）
│       ├── display.py               # set_entity_visibility(), set_display_mode(),
│       │                            # set_voxel_slice(), set_entity_opacity()
│       ├── camera.py                # create_view(), set_standard_view(),
│       │                            # focus_on_entity(), set_camera_pose()
│       └── capture.py               # capture_view(), add_scene_label()
│
├── database/                        # 数据库层
│   ├── __init__.py
│   ├── schema.sql                   # 建表 SQL（DuckDB，9 张表）
│   ├── db_manager.py                # 连接管理 + CRUD（单例）
│   └── models.py                    # Pydantic 数据模型（与表结构对应）
│
├── state/                           # LangGraph 共享状态
│   ├── __init__.py
│   └── graph_state.py               # GeoModelingState 定义
│
└── data/                            # 数据目录（运行时生成）
    ├── raw/                         # 原始输入数据（用户提供）
    ├── processed/                   # 中间处理结果（体素网格等）
    ├── models/                      # 生成的地质模型（VTK/NPZ/HDF5）
    └── output/                      # capture_view 截图输出（PNG）
```

---

## 智能体设计

### Planner Agent（规划协调器）

**文件**：`agents/planner.py`

| 属性 | 值 |
|------|-----|
| 类型 | `langgraph_supervisor` Supervisor |
| LLM | 由 `llm_factory` 按 `config.py` 创建 |
| 职责 | 任务分解、子任务路由、错误恢复 |

**路由逻辑**：Planner 根据自然语言指令判断需要调用哪些智能体，按 **初始化 → 预处理 → 建模 → 可视化** 顺序编排。

**修改 Planner 的 System Prompt**：

```python
# agents/planner.py 中的 _SUPERVISOR_PROMPT 字符串
_SUPERVISOR_PROMPT = """
...在此修改协调策略...
"""
```

---

### InitializationAgent（初始化）

**文件**：`agents/initialization.py`

负责工程层级注册和数据集管理，是整个工作流的第一步。

**工程层级工具**

| 工具 | 功能 |
|------|------|
| `register_project` | 注册工程项目（顶层，指定工程名称、类型、坐标系） |
| `register_centerline` | 注册中线（关联中线几何文件，定义里程起终点） |
| `register_work_site` | 注册工点（指定中线上的里程区间） |
| `register_alignment_segment` | 注册设计段落（围岩级别、开挖断面、支护参数） |
| `query_hierarchy` | 查询工程层级结构（project/centerline/work_site） |

**数据集工具**

| 工具 | 功能 |
|------|------|
| `register_dataset` | 注册数据集到元数据库（按 positioning_type 填写定位信息） |
| `query_metadata` | 按类型/里程范围/状态查询可用数据集 |
| `import_dataset` | 根据 dataset_id 获取文件路径和元信息 |
| `validate_data` | 质量验证，更新 `quality_flag` |

**坐标转换工具**

| 工具 | 功能 |
|------|------|
| `project_transform` | 地理空间数据的坐标系转换 |
| `mileage_to_coord` | 里程位置 → 大地坐标（用于空间关联） |
| `coord_to_mileage` | 大地坐标 → 中线里程（用于数据融合） |

**操作顺序**：
1. `query_hierarchy` 确认工程是否已存在
2. `register_project` → `register_centerline` → `register_work_site`（按需）
3. `register_dataset`（地表数据用 `spatial`，洞内数据用 `mileage`）
4. `validate_data` 验证质量

---

### PreprocessingAgent（预处理对齐）

**文件**：`agents/preprocessing.py`

| 工具 | 功能 |
|------|------|
| `clip_to_boundary` | 裁剪到研究区边界 |
| `resample` | 统一分辨率（bilinear/nearest/cubic/mean） |
| `voxelize` | 转换为三维体素网格（核心中间格式） |
| `spatial_sample` | 在指定坐标采样属性值 |
| `raster_to_vector` | 栅格转矢量（等高线、边界提取） |
| `normalize_attributes` | 属性标准化（minmax/zscore/log） |
| `filter_outliers` | 异常值过滤（statistical/radius/iqr） |

---

### ModelingAgent（地球科学建模）

**文件**：`agents/modeling.py`

工具按功能分组：

**插值与预测**

| 工具 | 功能 |
|------|------|
| `interpolate_spatial` | 从控制点插值生成连续属性场（IDW/Kriging/RBF） |
| `classify_lithology` | ML 方法预测三维岩性分布（RF/SVM/XGBoost/MLP） |

**曲面重建**

| 工具 | 功能 |
|------|------|
| `extract_stratigraphy` | 从钻孔分层提取地层界面 TIN |
| `delaunay_triangulation` | 散点集 Delaunay 三角剖分 |
| `extract_isosurface` | 属性场等值面提取（Marching Cubes） |

**结构建模**

| 工具 | 功能 |
|------|------|
| `model_geological_body` | 规则驱动地质体建模（倾角/走向/厚度） |
| `model_fault` | 三维断层面建模 |
| `boolean_operation` | 地质体布尔运算（切割/合并/差集） |

**集成输出**

| 工具 | 功能 |
|------|------|
| `merge_voxel_attributes` | 多属性体素融合（结构属性一体化） |
| `validate_model` | 钻孔交叉验证 + 地质合理性检查 |
| `export_model` | 导出 VTK/NPZ/HDF5/CSV + 注册到数据库 |

---

### VisualizationAgent（可视化控制）

**文件**：`agents/visualization.py`

通过 `DTPyRuntime` API 直接控制 DTGeoStudio 软件内置三维面板，所有操作实时作用于软件界面，无需导出中间文件。

**实体外观控制**

| 工具 | 功能 |
|------|------|
| `configure_entity` | 统一设置实体外观，一次调用可组合控制可见性、渲染模式（wireframe / solid / colormap）、透明度 |
| `set_voxel_slice` | 为体素模型设置切片面（X/Y/Z 轴），查看内部地质结构 |

**视图与相机控制**

| 工具 | 功能 |
|------|------|
| `create_view` | 新建视图（单视图 / 左右分屏 / 上下分屏 / 四视图） |
| `set_standard_view` | 切换标准视角：top / front / right / isometric 等 |
| `focus_on_entity` | 自动 fit 相机至目标实体；`orbit=True` 时同时将实体中心设为轨道旋转中心 |

**截图与标注**

| 工具 | 功能 |
|------|------|
| `capture_view` | 截取当前视图画面保存为图片 |
| `add_scene_label` | 在三维场景中添加文字标注（里程、地层名等） |

**典型工作流**：
1. `configure_entity`（visible=True, mode='colormap', attribute='lithology'）→ `focus_on_entity`
2. `set_voxel_slice`（体素切片）→ `set_standard_view`（调整视角）→ `capture_view`（保存截图）
3. `create_view × N`（多视图）→ 各视图 `focus_on_entity` + `set_standard_view`

**颜色表参考**：岩性/岩类 → `geological_lithology`；深度/厚度 → `viridis`；物性参数 → `jet` 或 `coolwarm`

---

## 工具清单

### 工具接口规范

所有工具函数遵循统一规范：

```python
from pydantic import BaseModel
from tools.common import ToolOutput
from langchain_core.tools import tool

class MyToolInput(BaseModel):
    param1: str          # 参数说明（供 LLM 理解）
    param2: float = 1.0  # 带默认值

@tool(args_schema=MyToolInput)
def my_tool(param1: str, param2: float = 1.0) -> dict:
    """
    工具的功能描述（供 LLM 决策是否调用）。

    详细说明、适用场景、注意事项。
    """
    try:
        # 接入自有库
        # from your_lib.module import func
        # result = func(param1, param2)
        raise NotImplementedError("请接入自有库实现")
    except NotImplementedError as e:
        return ToolOutput(success=False, message=str(e)).model_dump()
    except Exception as e:
        return ToolOutput(success=False, message=f"失败: {e}").model_dump()
```

### ToolOutput 标准返回结构

```python
class ToolOutput(BaseModel):
    success: bool                    # 是否成功
    data: Optional[Any] = None       # 小数据直接返回（列表、字典等）
    file_path: Optional[str] = None  # 大数据（体素网格等）返回文件路径
    message: str = ""                # 人类可读的结果说明
    metadata: dict = {}              # 附加元信息（文件大小、网格尺寸等）
```

---

## 数据库设计

**引擎**：DuckDB（`pip install duckdb`，零系统依赖）

**数据库文件**：`database/geo_metadata.duckdb`（运行时自动创建）

**设计原则**：DTAgents 只存储**元数据**，不存储实际数据内容。几何数据、点云、栅格等均通过 `file_path` 引用外部文件。

### 表结构（共 9 张）

```
工程层级：projects → centerlines → work_sites
设计参数：alignment_segments（基于中线里程）
数据管理：datasets → spatial_extents / mileage_extents
过程记录：processing_history
成果注册：model_registry
```

#### `projects`（工程项目表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `project_id` | VARCHAR PK | UUID |
| `name` | VARCHAR | 工程名称，如"某高速公路TJ01标" |
| `type` | VARCHAR | highway\|railway\|metro\|municipal\|waterway |
| `default_crs` | VARCHAR | 工程默认坐标系，如 EPSG:4547 |

#### `centerlines`（中线表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `centerline_id` | VARCHAR PK | UUID |
| `project_id` | VARCHAR FK | 所属工程 |
| `name` | VARCHAR | 如"正洞中线"、"1#斜井中线" |
| `type` | VARCHAR | main_tunnel\|pilot_tunnel\|inclined_shaft\|ramp... |
| `file_path` | VARCHAR | 中线几何文件路径（元数据引用） |
| `mileage_start` | DOUBLE | 起始里程（m） |
| `mileage_end` | DOUBLE | 终止里程（m） |

#### `work_sites`（工点表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `site_id` | VARCHAR PK | UUID |
| `centerline_id` | VARCHAR FK | 所属中线 |
| `project_id` | VARCHAR FK | 冗余，方便查询 |
| `name` | VARCHAR | 工点名称 |
| `type` | VARCHAR | tunnel\|bridge\|open_cut\|station\|culvert |
| `start_mileage` | DOUBLE | 工点起始里程（m） |
| `end_mileage` | DOUBLE | 工点终止里程（m） |

#### `alignment_segments`（设计段落表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `segment_id` | VARCHAR PK | UUID |
| `centerline_id` | VARCHAR FK | 所属中线 |
| `start_mileage` | DOUBLE | 段落起始里程 |
| `end_mileage` | DOUBLE | 段落终止里程 |
| `section_type` | VARCHAR | 断面形式 |
| `excavation_width` | DOUBLE | 开挖宽度（m） |
| `excavation_height` | DOUBLE | 开挖高度（m） |
| `rock_grade` | VARCHAR | 围岩级别：I\|II\|III\|IV\|V\|VI |
| `extra_params` | VARCHAR | JSON，其他类型特定的设计参数 |

#### `datasets`（数据集基础表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | VARCHAR PK | UUID |
| `project_id` | VARCHAR FK | 所属工程 |
| `site_id` | VARCHAR FK | 所属工点（可为 NULL，跨工点数据） |
| `name` | VARCHAR | 数据集名称 |
| `data_type` | VARCHAR | DEM/DOM/DRL/TSP/GPR/... |
| `positioning_type` | VARCHAR | spatial\|mileage\|both |
| `file_path` | VARCHAR | 数据文件路径（元数据引用） |
| `file_format` | VARCHAR | GeoTIFF\|SHP\|CSV\|LAS\|SEG-Y\|HDF5\|IFC... |
| `status` | VARCHAR | raw\|validated\|processed\|archived |
| `quality_flag` | INTEGER | 0未验证/1通过/2警告/3失败 |
| `tags` | VARCHAR | JSON 数组 |
| `extra_meta` | VARCHAR | JSON，类型特定属性 |

> 坐标/里程信息分别存于 `spatial_extents` 和 `mileage_extents`，不在本表。

#### `spatial_extents`（地理空间范围表）

适用：DEM DOM EGM 等地理坐标定位数据，与 `datasets` 1:1，仅 `positioning_type IN ('spatial', 'both')` 时存在。

| 字段 | 类型 | 说明 |
|------|------|------|
| `dataset_id` | VARCHAR PK FK | |
| `crs` | VARCHAR | 坐标系，如 EPSG:4547 |
| `bbox_minx/miny/maxx/maxy` | DOUBLE | 平面范围（X 东向，Y 北向） |
| `bbox_minz/maxz` | DOUBLE | 高程范围（m），二维数据为 NULL |
| `resolution_m` | DOUBLE | 空间分辨率（m），栅格数据填写 |

#### `mileage_extents`（里程范围表）

适用：TSP GPR TEM 等里程定位数据，与 `datasets` 1:1，仅 `positioning_type IN ('mileage', 'both')` 时存在。

| 字段 | 类型 | 说明 |
|------|------|------|
| `dataset_id` | VARCHAR PK FK | |
| `centerline_id` | VARCHAR FK | 所属中线（里程基于具体中线定义） |
| `start_mileage` | DOUBLE | 起始里程（m） |
| `end_mileage` | DOUBLE | 终止里程（m），NULL 表示点状数据 |
| `offset_lateral` | DOUBLE | 横向偏移（m，右正左负） |
| `offset_vertical` | DOUBLE | 竖向偏移（m，上正下负） |
| `face_id` | VARCHAR | 掌子面编号（TFR 数据使用） |
| `measurement_dir` | VARCHAR | forward\|backward（相对推进方向） |

#### `processing_history`（处理历史表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | BIGINT PK | 自增 |
| `project_id` | VARCHAR FK | 所属工程 |
| `site_id` | VARCHAR FK | 所属工点 |
| `agent_name` | VARCHAR | 执行智能体名称 |
| `tool_name` | VARCHAR | 调用工具名称 |
| `input_datasets` | VARCHAR | JSON 数组，输入数据集 ID |
| `output_datasets` | VARCHAR | JSON 数组，输出数据集 ID |
| `parameters` | VARCHAR | JSON，工具调用参数快照 |
| `status` | VARCHAR | pending\|running\|success\|failed |
| `duration_ms` | INTEGER | 执行耗时（ms） |

#### `model_registry`（地质模型注册表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | VARCHAR PK | UUID |
| `project_id` | VARCHAR FK | 所属工程 |
| `site_id` | VARCHAR FK | 所属工点 |
| `positioning_type` | VARCHAR | spatial\|mileage |
| `voxel_resolution` | DOUBLE | 体素分辨率（m） |
| `grid_nx/ny/nz` | INTEGER | 体素网格尺寸 |
| `crs_epsg` | INTEGER | 坐标系（spatial 模式） |
| `bbox_min/max x/y/z` | DOUBLE | 地理范围（spatial 模式） |
| `centerline_id` | VARCHAR FK | 关联中线（mileage 模式） |
| `start_mileage` | DOUBLE | 模型起始里程（mileage 模式） |
| `end_mileage` | DOUBLE | 模型终止里程（mileage 模式） |
| `model_radius` | DOUBLE | 建模半径（m，以中线为轴） |
| `file_path` | VARCHAR | VTK/NPZ/HDF5 文件路径 |
| `attributes` | VARCHAR | JSON 数组，模型包含的属性列表 |
| `input_dataset_ids` | VARCHAR | JSON 数组，来源数据集 |
| `processing_ids` | VARCHAR | JSON 数组，关联 processing_history |

### 数据库操作示例

```python
from database import db

# 初始化
db.connect()

# 查询工程层级
projects = db.query_hierarchy(level="project")

# 查询某里程范围内的 GPR 数据
results = db.query_datasets(
    data_type="GPR",
    centerline_id="<uuid>",
    start_mileage=12340,
    end_mileage=14200,
)

# 注册新数据集（里程定位）
from database.models import Dataset
ds = Dataset(
    name="旗山隧道进口GPR_DK12340",
    data_type="GPR",
    positioning_type="mileage",
    file_path="/path/to/gpr.json",
    project_id="<uuid>",
    site_id="<uuid>",
)
dataset_id = db.insert_dataset(ds)
```

---

## 状态设计

**文件**：`state/graph_state.py`

`GeoModelingState` 继承 `MessagesState`，在消息历史之上添加地球科学建模专用字段：

```python
class GeoModelingState(MessagesState):
    # 项目配置
    study_area_id: str               # 研究区 / 工点 ID
    voxel_resolution: float          # 体素分辨率（米）
    target_crs: str                  # 统一坐标系

    # 初始化结果
    loaded_dataset_ids: list[str]    # 已注册数据集 ID

    # 预处理结果（存路径，不存数组）
    aligned_data_paths: dict         # {data_type: file_path}
    voxel_grid_path: str             # 体素网格文件路径

    # 建模结果
    model_id: str                    # 模型注册 ID
    model_file_path: str             # VTK/NPZ 路径

    # 可视化输出
    output_files: list[str]          # 输出文件路径列表

    # 执行状态
    current_step: str
    error_log: list[str]
    processing_history_ids: list[int]
```

> **设计原则**：体素网格（512³×float32 ≈ 512MB）**不直接存入 State**，写入磁盘后将文件路径存入 State，避免序列化开销。

---

## 接入自有库

所有工具函数均为接口存根，实际算法由自有库提供。每个工具文件中有明确的 `# TODO` 注释标记接入点。

### 接入方式

以 `tools/preprocessing/voxelize.py` 为例：

```python
@tool(args_schema=VoxelizeInput)
def voxelize(file_path, data_type, resolution, bbox, target_crs, output_path=None):
    """..."""
    try:
        # ✅ 接入自有库：替换以下两行
        from your_lib.preprocessing import voxelize_data
        result = voxelize_data(file_path, data_type, resolution, bbox, target_crs, output_path)

        return ToolOutput(
            success=True,
            file_path=result["output_path"],
            message=f"体素化完成，网格尺寸: {result['nx']}x{result['ny']}x{result['nz']}",
            metadata=result,
        ).model_dump()
    except Exception as e:
        return ToolOutput(success=False, message=f"体素化失败: {e}").model_dump()
```

### 各工具接入点汇总

| 工具文件 | 函数 | 接入点 |
|---------|------|--------|
| `tools/initialization/transform.py` | `project_transform` | `your_lib.transform.crs_transform` |
| `tools/initialization/transform.py` | `mileage_to_coord` | `your_lib.centerline.mileage_to_coord` |
| `tools/initialization/transform.py` | `coord_to_mileage` | `your_lib.centerline.coord_to_mileage` |
| `tools/initialization/validation.py` | `validate_data` | `your_lib.validation.validate_dataset` |
| `tools/preprocessing/voxelize.py` | `voxelize` | `your_lib.preprocessing.voxelize_data` |
| `tools/preprocessing/resample.py` | `resample` | `your_lib.preprocessing.resample_grid` |
| `tools/preprocessing/resample.py` | `clip_to_boundary` | `your_lib.preprocessing.clip` |
| `tools/preprocessing/sampling.py` | `spatial_sample` | `your_lib.preprocessing.sample_at_coords` |
| `tools/preprocessing/normalize.py` | `normalize_attributes` | `your_lib.preprocessing.normalize` |
| `tools/preprocessing/normalize.py` | `filter_outliers` | `your_lib.preprocessing.filter_noise` |
| `tools/preprocessing/convert.py` | `raster_to_vector` | `your_lib.preprocessing.raster2vector` |
| `tools/modeling/interpolation.py` | `interpolate_spatial` | `your_lib.modeling.spatial_interpolation` |
| `tools/modeling/classification.py` | `classify_lithology` | `your_lib.modeling.ml_lithology_classify` |
| `tools/modeling/stratigraphy.py` | `extract_stratigraphy` | `your_lib.modeling.extract_strata_surfaces` |
| `tools/modeling/stratigraphy.py` | `model_geological_body` | `your_lib.modeling.rule_based_modeling` |
| `tools/modeling/surface.py` | `delaunay_triangulation` | `your_lib.modeling.delaunay_triangulation` |
| `tools/modeling/surface.py` | `extract_isosurface` | `your_lib.modeling.isosurface_extraction` |
| `tools/modeling/fault.py` | `model_fault` | `your_lib.modeling.fault_surface_modeling` |
| `tools/modeling/boolean_ops.py` | `boolean_operation` | `your_lib.modeling.mesh_boolean_op` |
| `tools/modeling/merge.py` | `merge_voxel_attributes` | `your_lib.modeling.merge_voxel_grids` |
| `tools/modeling/validation.py` | `validate_model` | `your_lib.modeling.model_validation` |
| `tools/modeling/export.py` | `export_model` | `your_lib.io.export_voxel_model` |
| `tools/visualization/display.py` | `set_entity_visibility` | `DTPyRuntime` API |
| `tools/visualization/display.py` | `set_display_mode` | `DTPyRuntime` API |
| `tools/visualization/display.py` | `set_voxel_slice` | `DTPyRuntime` API |
| `tools/visualization/display.py` | `set_entity_opacity` | `DTPyRuntime` API |
| `tools/visualization/camera.py` | `create_view` | `DTPyRuntime` API |
| `tools/visualization/camera.py` | `set_standard_view` | `DTPyRuntime` API |
| `tools/visualization/camera.py` | `focus_on_entity` | `DTPyRuntime` API |
| `tools/visualization/camera.py` | `set_camera_pose` | `DTPyRuntime` API |
| `tools/visualization/capture.py` | `capture_view` | `DTPyRuntime` API |
| `tools/visualization/capture.py` | `add_scene_label` | `DTPyRuntime` API |

> **注意**：
> - `register_project/centerline/work_site/alignment_segment`（`hierarchy.py`）、`register_dataset`（`register.py`）、`query_metadata/query_hierarchy`（`query.py`）、`import_dataset`（`readers.py`）已完整实现数据库交互逻辑，无需额外接入。
> - `tools/visualization/` 下的所有工具均通过 `DTPyRuntime` 与 DTGeoStudio 交互，需确保 `DTPyRuntime` 已正确安装（`import DTPyRuntime as dtpr` 可成功导入）。

---

## 扩展指南

### 添加新工具

1. 在对应的 `tools/<category>/` 目录下创建或修改文件
2. 定义 `Input` Pydantic 模型 + `@tool` 装饰器函数
3. 在该目录的 `__init__.py` 中导出
4. 在对应的 `agents/<agent>.py` 的 `_TOOLS` 列表中添加
5. 更新 `agents/<agent>.py` 的 `_SYSTEM_PROMPT` 说明新工具用途

```python
# 示例：添加 uncertainty_estimation 工具
# 1. 新建 tools/modeling/uncertainty.py
@tool(args_schema=UncertaintyInput)
def estimate_uncertainty(model_path: str, method: str = "bootstrap") -> dict:
    """估算地质模型各体素的预测不确定性..."""
    ...

# 2. 在 tools/modeling/__init__.py 中添加
from .uncertainty import estimate_uncertainty

# 3. 在 agents/modeling.py 的 _TOOLS 中添加
from tools.modeling import ..., estimate_uncertainty
_TOOLS = [..., estimate_uncertainty]
```

### 添加新数据类型

1. 在 `config.py` 的 `DATA_TYPES` 列表中添加代码，并按定位类型加入 `SPATIAL_DATA_TYPES` 或 `MILEAGE_DATA_TYPES`
2. 在 `tools/initialization/readers.py` 的 `import_dataset` 中添加分发逻辑
3. 在 `tools/preprocessing/voxelize.py` 的 `voxelize` 中添加该类型的体素化策略
4. 更新相关智能体的 `_SYSTEM_PROMPT` 说明新类型的处理方式

### 更换 LLM

修改环境变量或 `config.py`：

```bash
# Anthropic（默认）
export LLM_PROVIDER=anthropic
export LLM_MODEL=claude-opus-4-6        # 最强推理
# export LLM_MODEL=claude-sonnet-4-6   # 性价比均衡
# export LLM_MODEL=claude-haiku-4-5-20251001  # 最快速

# OpenAI
export LLM_PROVIDER=openai
export LLM_MODEL=gpt-4o

# DeepSeek（经济高效）
export LLM_PROVIDER=deepseek
export DEEPSEEK_API_KEY=sk-...

# 阿里云通义千问
export LLM_PROVIDER=qwen
export LLM_MODEL=qwen-max
export DASHSCOPE_API_KEY=...

# Google Gemini
export LLM_PROVIDER=gemini
export LLM_MODEL=gemini-2.0-flash
export GOOGLE_API_KEY=...
```

或在 `agents/planner.py` 中为特定智能体单独配置：

```python
# 规划器用最强模型，子智能体用快速模型
from llm_factory import create_llm
planner_llm = create_llm(provider="anthropic", model="claude-opus-4-6")
worker_llm  = create_llm(provider="anthropic", model="claude-haiku-4-5-20251001")
data_agent  = create_initialization_agent(worker_llm)
```

### 更换数据库

当前使用 DuckDB。若需切换至 SpatiaLite：

1. 修改 `database/schema.sql`（将 DuckDB 语法改为 SQLite）
2. 修改 `database/db_manager.py`（将 `duckdb.connect` 改为 `sqlite3.connect` + spatialite 扩展）
3. 修改 `requirements.txt`（替换 `duckdb` 为 `spatialite`）

### 修改 State 字段

在 `state/graph_state.py` 中直接添加字段：

```python
class GeoModelingState(MessagesState):
    ...
    # 新增：不确定性分析结果
    uncertainty_map_path: Optional[str] = None
    # 新增：断层信息
    fault_mesh_paths: list[str] = []
```

---

## 配置参考

**文件**：`config.py`

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `BASE_DIR` | 项目根目录 | 自动推断 |
| `DB_PATH` | `database/geo_metadata.duckdb` | 数据库文件路径 |
| `LLM_PROVIDER` | `anthropic` | LLM 提供商（anthropic\|openai\|deepseek\|qwen\|gemini） |
| `LLM_MODEL` | `""`（使用 provider 默认值） | LLM 模型 ID，可通过环境变量或 `--model` 覆盖 |
| `LLM_TEMPERATURE` | `0` | 温度（0=确定性，推荐） |
| `LLM_MAX_TOKENS` | `4096` | 最大输出 token 数 |
| `DEFAULT_VOXEL_RESOLUTION` | `5.0` | 默认体素分辨率（米） |
| `DEFAULT_TARGET_CRS` | `EPSG:4547` | 默认目标坐标系 |
| `DEFAULT_DEPTH_MIN` | `-200.0` | 建模深度下限（米） |
| `DEFAULT_DEPTH_MAX` | `0.0` | 建模深度上限（米） |
| `SPATIAL_DATA_TYPES` | `[DEM, DOM, DRL, EGM, BIM]` | 地理坐标定位数据类型 |
| `MILEAGE_DATA_TYPES` | `[TSP, TEM, GPR, ...]` | 里程坐标定位数据类型 |
| `LANGGRAPH_RECURSION_LIMIT` | `100` | 图递归深度上限 |

---

## 开放问题

以下问题在实现自有库时需要明确：

### 1. 中线几何文件格式
`register_centerline` 记录中线文件路径（DXF/SHP/GeoJSON/LandXML/CSV），实际几何解析和里程计算由 `mileage_to_coord` / `coord_to_mileage` 依赖的 `your_lib.centerline` 负责。需确认中线文件的格式约定和里程零点定义。

### 2. 钻孔分层数据格式
`extract_stratigraphy` 要求钻孔数据包含字段：`hole_id, x, y, z_top, z_bottom, lithology_code`。
若原始钻孔数据格式不同，需在 `import_dataset` 中添加字段映射逻辑（通过 `options` 参数传入 `field_map`）。

### 3. BIM 坐标系转换
IFC 文件通常使用局部坐标系。`project_transform` 需要 IFC → 地理坐标的变换矩阵。建议将变换参数存入 `datasets.extra_meta` 字段。

### 4. 多源数据融合策略
`merge_voxel_attributes` 的 `priority` 策略的优先级顺序需根据地质专业判断定义，建议以配置文件形式管理：
```python
# config.py 中添加
ATTRIBUTE_PRIORITY = {
    "lithology": ["drillhole", "ml_classification", "rule_based"],
}
```

### 5. 体素分辨率策略
当前为全局统一分辨率。若需多分辨率支持（地表精细 + 深部粗糙），需修改 `GeoModelingState` 添加分辨率分层配置，并修改 `voxelize` 和 `merge_voxel_attributes` 的网格对齐逻辑。

### 6. 地球物理数据格式
`TSP`（地震）/ `GPR`（探地雷达）/ `TEM`（瞬变电磁）的读取接口（`import_dataset`）需在 `your_lib.readers` 中实现具体的格式解析，当前仅返回文件路径。

---

## 依赖说明

```
# Web API（前端后端）
fastapi>=0.111
uvicorn[standard]>=0.29

# 智能体框架
langgraph>=0.2
langgraph-supervisor>=0.0.11
langchain-anthropic>=0.3
langchain-openai>=0.2

# 数据库
duckdb>=0.10

# 数据模型
pydantic>=2.5
numpy>=1.26
```

> - 数据读取、预处理、建模、可视化均由**自有库**提供，框架层不引入第三方数据处理依赖（gdal、vtk、scipy 等）。
> - 可视化智能体通过 `DTPyRuntime` 与 DTGeoStudio 交互，需单独安装（不在 `requirements.txt` 中）。
