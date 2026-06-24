"""全局配置 - 路径、模型、分辨率等"""
import os
from pathlib import Path

# ——— 项目根目录 ———
BASE_DIR = Path(__file__).parent

# ——— 数据目录 ———
DATA_DIR = BASE_DIR / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
MODELS_DIR = DATA_DIR / "models"
OUTPUT_DIR = DATA_DIR / "output"

# ——— 数据库配置 ———
DB_PATH = BASE_DIR / "database" / "geo_metadata.duckdb"

# ——— LLM 配置 ———
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "anthropic")  # anthropic | openai
LLM_MODEL = os.environ.get("LLM_MODEL", "")                 # 空字符串 = 使用 provider 默认值
LLM_TEMPERATURE = 0
LLM_MAX_TOKENS = 8000
LLM_DEBUG: bool = os.environ.get("LLM_DEBUG", "false").lower() == "true"  # 打印每次 LLM 调用的 messages

# ——— 默认建模参数 ———
DEFAULT_VOXEL_RESOLUTION = 5.0      # 体素分辨率（米）
DEFAULT_TARGET_CRS = "EPSG:4547"    # 默认目标坐标系（CGCS2000 / 3-degree Gauss-Kruger CM 114E）
DEFAULT_DEPTH_MIN = -200.0          # 默认建模深度下限（米）
DEFAULT_DEPTH_MAX = 0.0             # 默认建模深度上限（米）

# ——— 支持的数据类型 ———
DATA_TYPES = [
    # 工程 / 区域类（地理坐标定位）
    "DEM",      # 数字高程模型
    "DOM",      # 数字正射影像
    "DRL",      # 踏勘钻孔数据
    "EGM",      # 工程地质图
    "BIM",      # 建筑信息模型

    # 洞内 / 里程类（里程定位）
        # 超前地质预报
    "TSP",      # 隧道地震波反射
    "TEM",      # 洞内瞬变电磁
    "GPR",      # 洞内地质雷达
    "AHD",      # 超前水平钻
    "DBH",      # 加深炮孔
        # 掌子面观测
    "TFR",      # 影像、扫描、地质编录
        # 机械设备
    "TBM",      # 隧道掘进机
    "RDR"       # 凿岩台车
        # 原位试验
    "IST"       # 硬度、应力、岩石稳定性
        # 环境监测
    "EMS"       # 温度、湿度、有毒有害气体
]

# 定位类型
POSITIONING_TYPES = ["spatial", "mileage", "both"]

# 按定位类型分组（供 Agent 参考）
SPATIAL_DATA_TYPES  = ["DEM", "DOM", "DRL", "EGM", "BIM"]
MILEAGE_DATA_TYPES  = ["TSP", "TEM", "GPR", "AHD", "DBH", 
                       "TFR", "TBM", "RDR", "IST", "EMS"]

# ——— 可视化输出格式 ———
VIZ_FORMATS = ["vtk", "gltf", "threejs_json"]

# ——— LangGraph 递归限制 ———
LANGGRAPH_RECURSION_LIMIT = 100

# ——— 检索结果确认阈值 ———
# query_metadata 返回条数超过此值时，仅返回摘要并要求用户确认，防止 token 爆炸
QUERY_RESULT_CONFIRM_THRESHOLD: int = int(os.environ.get("QUERY_RESULT_CONFIRM_THRESHOLD", "128"))

# ——— 消息压缩阈值（跨轮历史压缩，由 compress_history_* 使用）———
# 历史消息条数超过此值时触发摘要压缩
MSG_COMPRESS_THRESHOLD: int = int(os.environ.get("MSG_COMPRESS_THRESHOLD", "25"))
# 估算字符数超过此值时强制压缩（1字符≈1token）
TOKEN_COMPRESS_THRESHOLD: int = int(os.environ.get("TOKEN_COMPRESS_THRESHOLD", "5000"))
# 压缩后保留的最近消息条数（不纳入摘要的尾部消息）
MSG_KEEP_RECENT: int = int(os.environ.get("MSG_KEEP_RECENT", "5"))

# ——— Graph 内部 LLM 调用上下文裁剪阈值（由 pre_model_hook 使用）———
# supervisor 每次 LLM 调用前，若消息体积超过此字符数则裁剪旧消息
SUPERVISOR_CTX_CHARS: int = int(os.environ.get("SUPERVISOR_CTX_CHARS", "5000"))
# 子 Agent 每次 LLM 调用前，消息体积上限（字符数）
AGENT_CTX_CHARS: int = int(os.environ.get("AGENT_CTX_CHARS", "1500"))

# ——— API 密钥（从环境变量读取）———
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY    = os.environ.get("OPENAI_API_KEY", "")
DEEPSEEK_API_KEY  = os.environ.get("DEEPSEEK_API_KEY", "")
DASHSCOPE_API_KEY = os.environ.get("DASHSCOPE_API_KEY", "") 
GOOGLE_API_KEY    = os.environ.get("GOOGLE_API_KEY", "") 
