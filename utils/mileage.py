"""里程字符串解析工具

中国铁路/公路里程格式：[冠号][公里数]+[米数]
  例：X1DK2+539  → prefix="X1DK", 2539.0 m
      DK14+200   → prefix="DK",   14200.0 m
      ZDK5+100   → prefix="ZDK",  5100.0 m
      K25+500    → prefix="K",    25500.0 m
      YDK3+400.5 → prefix="YDK",  3400.5 m

冠号规律：末尾必须是字母 K（如 DK、ZDK、YDK、X1DK、K）。
"""
from __future__ import annotations

import re
from typing import Optional

# 里程字符串正则：冠号（末位为K）+ 公里数 + "+" + 米数
_MILEAGE_RE = re.compile(
    r"^([A-Za-z0-9]*K)"   # 冠号（必须以 K 结尾）
    r"(\d+)"              # 公里数（整数）
    r"\+"                 # 分隔符
    r"(\d+(?:\.\d+)?)$",  # 米数（允许小数）
    re.IGNORECASE,
)


def parse_mileage_str(s: str) -> tuple[str, float]:
    """解析里程字符串，返回 (冠号, 里程值_m)。

    Args:
        s: 里程字符串，如 "X1DK2+539"、"DK14+200"

    Returns:
        (prefix, mileage_m)，例如 ("X1DK", 2539.0)

    Raises:
        ValueError: 格式不符合规范时抛出
    """
    s = s.strip()
    m = _MILEAGE_RE.match(s)
    if not m:
        raise ValueError(
            f"无法解析里程字符串: {s!r}，"
            "期望格式为 [冠号]km+m，如 'X1DK2+539'、'DK14+200'"
        )
    prefix = m.group(1).upper()
    km = int(m.group(2))
    meters = float(m.group(3))
    return prefix, km * 1000.0 + meters


def extract_prefix(s: str) -> Optional[str]:
    """从里程字符串中提取冠号，解析失败返回 None。"""
    try:
        prefix, _ = parse_mileage_str(s)
        return prefix
    except ValueError:
        return None
