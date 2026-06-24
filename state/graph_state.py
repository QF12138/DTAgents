"""LangGraph 共享状态定义"""
from typing import Optional
from langgraph.graph import MessagesState


class GeoModelingState(MessagesState):
    """三维空间建模多智能体系统共享状态。

    大型数组数据（体素网格等）不直接存入 State，而是写入磁盘后
    将文件路径存入 State，避免序列化开销和内存压力。
    """

    # ——— 项目配置 ———
    study_area_id: str = ""
    voxel_resolution: float = 5.0        # 体素分辨率（米）
    target_crs: str = "EPSG:4547"        # 统一坐标系 EPSG 码

    # ——— 初始化结果 ———
    loaded_dataset_ids: list[str] = []   # 已加载数据集 ID 列表
    centerline_id: str = ""              # 当前工点中线数据集 ID（ECL 类型）
    profile_id: str = ""                 # 当前工点设计断面数据集 ID

    # ——— 预处理结果 ———
    # key = 数据类型（DEM/DOM/DRL 等），value = 处理后文件路径
    aligned_data_paths: dict = {}
    voxel_grid_path: Optional[str] = None    # 体素网格文件路径（NPZ/HDF5）

    # ——— 建模结果 ———
    model_id: Optional[str] = None           # 注册的模型 ID（model_registry）
    model_file_path: Optional[str] = None    # VTK/NPZ 路径

    # ——— 可视化输出 ———
    output_files: list[str] = []             # 生成的文件路径列表

    # ——— 执行状态 ———
    current_step: str = "init"
    error_log: list[str] = []
    processing_history_ids: list[int] = []
