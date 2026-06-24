"""
将隧道中线数据（index.txt）入库（datasets + spatial_extents + mileage_extents）

参数（位置参数，按顺序输入）：
  1. abbr       工程简写，如 KDTK
  2. project_id 工程 UUID
  3. proj_name  工程名称，如 康定隧道
  4. folder     中线数据文件夹路径，如 E:/Datasets/.../DK278+100.000~DK300+800.000
  5. prefix     中线冠号，如 DK / X1DK / PDK

用法示例：
  python import_centerline.py KDTK <uuid> 康定隧道 E:/.../DK278+100.000~DK300+800.000 DK
  python import_centerline.py KDTK <uuid> 康定隧道 E:/.../DK278+100.000~DK300+800.000 DK --dry-run
"""

from __future__ import annotations

import argparse
import math
import os
import re
import sys
from pathlib import Path
from typing import Optional

import requests

# ──────────────────────────────────────────────────────────────────────────────
# 默认配置
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_API_BASE = "http://localhost:8000"
DEFAULT_CRS      = "EPSG:4543"

# ──────────────────────────────────────────────────────────────────────────────
# 冠号 → 具体信息（用于拼接 description）
# ★ 如需新增冠号，在此字典中补充 ★
# ──────────────────────────────────────────────────────────────────────────────
PREFIX_DETAIL: dict[str, str] = {
    "DK":     "正洞",
    "D3K":    "正洞",
    "D4K":    "正洞",
    "PDK":    "平导",
    "X1DK":   "2号斜井",
    "X2DK":   "3号斜井",
    "H1DK":   "1号横洞",
    "H2DK":   "2号横洞",
    # 补充其他冠号...
}


# ──────────────────────────────────────────────────────────────────────────────
# 里程解析
# ──────────────────────────────────────────────────────────────────────────────

def parse_mileage_str(mileage_str: str) -> float:
    """
    将里程字符串解析为浮点数（米）。

    示例：
      "DK278+100.000"  → 278*1000 + 100.0  = 278100.0
      "X1DK3+905.000"  → 3*1000   + 905.0  =   3905.0
      "X1DK0+015.500"  → 0*1000   + 15.5   =     15.5
      "PDK279+705.030" → 279*1000 + 705.03 = 279705.03
      "D3K278+100.000" → 278*1000 + 100.0  = 278100.0

    采用正则从字符串中提取最后一个 <km>+<m> 模式，以兼容冠号含数字的情况
    （如 X1DK、D3K、H1DK 等）。
    """
    # 找到最后一个 "整数 + 小数" 模式（km+m）
    # 使用 findall 后取最后一个匹配，确保冠号中嵌入的数字不被误识别
    matches = re.findall(r'(\d+)\+(\d+(?:\.\d+)?)', mileage_str.strip())
    if not matches:
        raise ValueError(f"无法解析里程字符串: {mileage_str!r}")
    km_str, m_str = matches[-1]   # 取最后一个匹配（最靠近 + 的 km 数字）
    return int(km_str) * 1000 + float(m_str)


def parse_folder_mileage(folder_name: str) -> tuple[float, float]:
    """
    从文件夹名称解析起止里程，返回 (start_m, end_m)，start <= end。

    示例：
      "DK278+100.000~DK300+800.000" → (278100.0, 300800.0)
      "X1DK3+905.000~X1DK0+000.000" → (0.0, 3905.0)
    """
    if '~' not in folder_name:
        raise ValueError(f"文件夹名称格式不符（缺少 ~）: {folder_name!r}")
    left, right = folder_name.split('~', 1)
    a = parse_mileage_str(left)
    b = parse_mileage_str(right)
    return (min(a, b), max(a, b))


# ──────────────────────────────────────────────────────────────────────────────
# 空间包围盒计算
# ──────────────────────────────────────────────────────────────────────────────

def compute_bbox(txt_path: Path) -> dict:
    """
    逐行读取 index.txt（X Y Z，空格分隔），计算 3D 包围盒。
    返回 {"minx", "miny", "maxx", "maxy", "minz", "maxz"}。
    """
    minx = miny = minz =  math.inf
    maxx = maxy = maxz = -math.inf
    count = 0

    with txt_path.open("r", encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            try:
                x, y, z = float(parts[0]), float(parts[1]), float(parts[2])
            except ValueError:
                continue
            if x < minx: minx = x
            if x > maxx: maxx = x
            if y < miny: miny = y
            if y > maxy: maxy = y
            if z < minz: minz = z
            if z > maxz: maxz = z
            count += 1

    if count == 0:
        raise ValueError(f"index.txt 中未读取到有效坐标点: {txt_path}")

    print(f"    共读取 {count} 个坐标点")
    return {
        "bbox_minx": round(minx, 6),
        "bbox_miny": round(miny, 6),
        "bbox_maxx": round(maxx, 6),
        "bbox_maxy": round(maxy, 6),
        "bbox_minz": round(minz, 6),
        "bbox_maxz": round(maxz, 6),
    }


# ──────────────────────────────────────────────────────────────────────────────
# API
# ──────────────────────────────────────────────────────────────────────────────

def get_project_crs(api_base: str, project_id: str) -> str:
    """从工程信息获取默认坐标系，失败时回退 DEFAULT_CRS。"""
    try:
        resp = requests.get(
            f"{api_base}/api/projects/{project_id}", timeout=10
        )
        if resp.status_code == 200:
            return resp.json().get("default_crs") or DEFAULT_CRS
    except Exception:
        pass
    return DEFAULT_CRS


def post_dataset(api_base: str, payload: dict) -> Optional[str]:
    resp = requests.post(
        f"{api_base}/api/datasets", json=payload, timeout=30
    )
    if resp.status_code == 201:
        return resp.json().get("id")
    print(f"  [FAIL] HTTP {resp.status_code}: {resp.text[:400]}")
    return None


# ──────────────────────────────────────────────────────────────────────────────
# 主流程
# ──────────────────────────────────────────────────────────────────────────────

def import_centerline(
    abbr:       str,
    project_id: str,
    proj_name:  str,
    folder:     str,
    prefix:     str,
    api_base:   str,
    dry_run:    bool,
) -> None:
    folder_path = Path(folder).resolve()
    if not folder_path.is_dir():
        print(f"[ERROR] 文件夹不存在: {folder_path}")
        sys.exit(1)

    txt_path = folder_path / "index.txt"
    if not txt_path.exists():
        print(f"[ERROR] 找不到 index.txt: {txt_path}")
        sys.exit(1)

    # ── 1. 里程解析（从文件夹名称）────────────────────────────────────────────
    folder_name = folder_path.name
    try:
        start_mileage, end_mileage = parse_folder_mileage(folder_name)
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    print(f"里程范围：{start_mileage} ~ {end_mileage} m")

    # ── 2. 空间包围盒（读取 index.txt）────────────────────────────────────────
    print("正在计算空间包围盒（读取 index.txt）...")
    try:
        bbox = compute_bbox(txt_path)
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    print(
        f"  X: {bbox['bbox_minx']} ~ {bbox['bbox_maxx']}\n"
        f"  Y: {bbox['bbox_miny']} ~ {bbox['bbox_maxy']}\n"
        f"  Z: {bbox['bbox_minz']} ~ {bbox['bbox_maxz']}"
    )

    # ── 3. 组装 datasets 字段 ───────────────────────────────────────────────
    name        = f"{abbr}-ECL-{prefix}"
    detail      = PREFIX_DETAIL.get(prefix, prefix)
    description = f"{proj_name}{detail}中线"
    file_size_mb = round(txt_path.stat().st_size / (1024 * 1024), 6)

    # 从工程获取 CRS
    if dry_run:
        crs = DEFAULT_CRS
    else:
        crs = get_project_crs(api_base, project_id)

    payload = {
        "project_id":       project_id,
        "name":             name,
        "data_type":        "ECL",
        "positioning_type": "both",
        "file_path":        str(txt_path).replace("\\", "/"),
        "file_format":      "txt",
        "file_size_mb":     file_size_mb,
        "description":      description,
        # 空间范围子对象
        "spatial": {
            "crs":        crs,
            "bbox_minx":  bbox["bbox_minx"],
            "bbox_miny":  bbox["bbox_miny"],
            "bbox_maxx":  bbox["bbox_maxx"],
            "bbox_maxy":  bbox["bbox_maxy"],
            "bbox_minz":  bbox["bbox_minz"],
            "bbox_maxz":  bbox["bbox_maxz"],
            "map_scale":  "1:2000",
        },
        # 里程范围子对象
        "mileage": {
            "start_mileage":  start_mileage,
            "end_mileage":    end_mileage,
            "measurement_dir": "forward",
        },
    }

    print(f"\n数据集信息：")
    print(f"  name:             {name}")
    print(f"  description:      {description}")
    print(f"  file_path:        {payload['file_path']}")
    print(f"  file_size_mb:     {file_size_mb} MB")
    print(f"  mileage:          {start_mileage} ~ {end_mileage} m")
    print(f"  crs:              {crs}")
    print(f"  map_scale:        1:2000")

    if dry_run:
        print("\n[DRY-RUN] 不写库，退出。")
        return

    # ── 4. 入库 ─────────────────────────────────────────────────────────────
    print("\n正在写入数据库...")
    did = post_dataset(api_base, payload)
    if did:
        print(f"[OK] 中线数据集已入库  id={did}")
    else:
        print("[FAIL] 入库失败，请检查 API 服务和日志。")
        sys.exit(1)


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="将隧道中线 index.txt 入库（datasets + spatial_extents + mileage_extents）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
参数说明：
  abbr        工程简写，如 KDTK
  project_id  工程 UUID
  proj_name   工程名称，如 康定隧道
  folder      中线数据文件夹路径（含 index.txt）
  prefix      中线冠号，如 DK / X1DK / PDK

示例：
  python import_centerline.py KDTK <uuid> 康定隧道 E:/.../DK278+100.000~DK300+800.000 DK
        """,
    )
    parser.add_argument("abbr",       help="工程简写（如 KDTK）")
    parser.add_argument("project_id", help="工程 UUID")
    parser.add_argument("proj_name",  help="工程名称（如 康定隧道）")
    parser.add_argument("folder",     help="中线数据文件夹路径（含 index.txt）")
    parser.add_argument("prefix",     help="中线冠号（如 DK / X1DK / PDK）")
    parser.add_argument(
        "--api-base", default=DEFAULT_API_BASE,
        help=f"API 服务地址（默认 {DEFAULT_API_BASE}）",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仅解析计算，不实际写库",
    )
    args = parser.parse_args()

    import_centerline(
        abbr       = args.abbr,
        project_id = args.project_id,
        proj_name  = args.proj_name,
        folder     = args.folder,
        prefix     = args.prefix,
        api_base   = args.api_base.rstrip("/"),
        dry_run    = args.dry_run,
    )


if __name__ == "__main__":
    main()
