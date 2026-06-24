"""工具接口公共基础类"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


class ToolOutput(BaseModel):
    """所有工具函数的标准化返回结构。"""

    success: bool
    data: Optional[Any] = None       # 小数据直接返回
    file_path: Optional[str] = None  # 大数据返回文件路径
    message: str = ""
    metadata: dict[str, Any] = {}
