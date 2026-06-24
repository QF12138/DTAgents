"""
批量将隧道检测数据文件夹入库（datasets + mileage_extents）

目录结构：
  <data_root>/
    <site_folder>/                ← 工点文件夹（如 208058）
      config.json                 ← 含 name 字段，用于检索 site_id
      <TYPE_folder>/              ← 数据类型文件夹（如 TSP、AHD）
        <data_folder>/            ← 单次检测数据文件夹
          index.json              ← 元数据

用法：
  python import_datasets_from_folder.py <data_root> <project_id> [options]

示例：
  python import_datasets_from_folder.py E:/Datasets/.../10750 your-project-uuid
  python import_datasets_from_folder.py E:/Datasets/.../10750 your-project-uuid --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Optional

import requests

# ──────────────────────────────────────────────────────────────────────────────
# 默认配置
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_API_BASE = "http://localhost:8000"

# ──────────────────────────────────────────────────────────────────────────────
# 工具函数
# ──────────────────────────────────────────────────────────────────────────────

def folder_size_mb(folder: Path) -> float:
    """递归计算文件夹下所有文件总大小（MB）。"""
    total = sum(f.stat().st_size for f in folder.rglob("*") if f.is_file())
    return round(total / (1024 * 1024), 4)


def format_mileage_name(dkname: str, dkilo: float) -> str:
    """
    将 dkilo 转换为里程字符串，拼接 dkname。
    例：dkname="X1DK", dkilo=3846   → "X1DK3+846"
         dkname="X1DK", dkilo=3818.8 → "X1DK3+818.8"
    """
    int_part = int(dkilo) // 1000
    remainder = dkilo - int_part * 1000
    # 余数格式化：整数值去掉小数点
    if remainder == int(remainder):
        rem_str = str(int(remainder))
    else:
        # 保留必要小数位，去除末尾多余 0
        rem_str = f"{remainder:.3f}".rstrip("0").rstrip(".")
    return f"KD-{dkname}{int_part}+{rem_str}"


def calc_end_mileage(dkilo: float, length: float,
                     construction_direction: Optional[str]) -> float:
    """
    根据施工方向计算 end_mileage。
    forward  → end = dkilo + length
    backward → end = dkilo - length
    """
    if construction_direction == "backward":
        return dkilo - length
    return dkilo + length   # forward 或 None 均按正向处理


# ──────────────────────────────────────────────────────────────────────────────
# API 辅助
# ──────────────────────────────────────────────────────────────────────────────

def fetch_all_work_sites(api_base: str, project_id: str) -> list[dict]:
    """分页拉取工程下所有工点，返回列表。"""
    sites: list[dict] = []
    page, size = 1, 100
    while True:
        resp = requests.get(
            f"{api_base}/api/work-sites",
            params={"project_id": project_id, "page": page, "size": size},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        items: list[dict] = data.get("items", [])
        sites.extend(items)
        if len(items) < size:
            break
        page += 1
    return sites


def post_dataset(api_base: str, payload: dict) -> Optional[str]:
    """POST /api/datasets，返回新建记录的 id，失败返回 None。"""
    resp = requests.post(
        f"{api_base}/api/datasets",
        json=payload,
        timeout=15,
    )
    if resp.status_code == 201:
        return resp.json().get("id")
    print(f"      [FAIL] HTTP {resp.status_code}: {resp.text[:300]}")
    return None


# ──────────────────────────────────────────────────────────────────────────────
# 核心入库逻辑
# ──────────────────────────────────────────────────────────────────────────────

def process_data_folder(
    data_folder: Path,
    dtype: str,
    project_id: str,
    site_id: str,
    construction_direction: Optional[str],
    api_base: str,
    dry_run: bool,
) -> bool:
    """处理单个数据文件夹（含 index.json），入库 datasets + mileage_extents。"""
    index_path = data_folder / "index.json"
    if not index_path.exists():
        print(f"      [SKIP] 无 index.json: {data_folder.name}")
        return False

    try:
        with index_path.open("r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception as e:
        print(f"      [SKIP] index.json 解析失败 ({data_folder.name}): {e}")
        return False

    dkilo = meta.get("dkilo")
    dkname = meta.get("dkname", "")
    length = meta.get("length") or 0.0
    monitor_date: Optional[str] = meta.get("monitordate")

    if dkilo is None:
        print(f"      [SKIP] index.json 缺少 dkilo: {data_folder.name}")
        return False

    dkilo = float(dkilo)
    length = float(length)

    # dataset.name
    name = format_mileage_name(dkname, dkilo)

    # description
    if dtype == 'TFS':
        description = meta.get("dzsm_zzmms", "")
    elif dtype == 'TEM':
        description = meta.get("suggestion", "")
    else:
        description = meta.get("conclusionyb", "")


    # file_size_mb
    size_mb = folder_size_mb(data_folder)

    # survey_date_start：取日期部分（去掉时间）
    survey_date_start: Optional[str] = None
    if monitor_date:
        survey_date_start = monitor_date.split(" ")[0]

    # mileage
    start_mileage = dkilo
    end_mileage = calc_end_mileage(dkilo, length, construction_direction)

    payload = {
        "project_id":       project_id,
        "site_id":          site_id,
        "name":             name,
        "data_type":        dtype,
        "positioning_type": "mileage",
        "file_path":        str(data_folder).replace("\\", "/"),
        "file_format":      "json",
        "file_size_mb":     size_mb,
        "survey_date_start": survey_date_start,
        "description":      description,
        "mileage": {
            "start_mileage":  start_mileage,
            "end_mileage":    end_mileage,
            "measurement_dir": "forward",
        },
    }

    if dry_run:
        print(
            f"      [DRY-RUN] {name}  {dtype}  "
            f"{start_mileage}~{end_mileage:.1f}m  size={size_mb}MB"
        )
        return True

    did = post_dataset(api_base, payload)
    if did:
        print(
            f"      [OK] {name}  {dtype}  "
            f"{start_mileage}~{end_mileage:.1f}m  → id={did}"
        )
        return True
    return False


def import_all(
    data_root: str,
    project_id: str,
    api_base: str,
    dry_run: bool,
) -> None:
    root = Path(data_root)
    if not root.is_dir():
        print(f"[ERROR] 目录不存在: {root}")
        sys.exit(1)

    # ── 1. 拉取所有工点，构建 name → site 信息 的查找字典 ──────────────────
    print(f"正在从 API 拉取工程 {project_id} 的工点列表...")
    if dry_run:
        print("  [DRY-RUN] 跳过 API 拉取，工点 construction_direction 均视为 None")
        site_lookup: dict[str, dict] = {}
    else:
        try:
            sites = fetch_all_work_sites(api_base, project_id)
        except Exception as e:
            print(f"[ERROR] 拉取工点失败: {e}")
            sys.exit(1)
        # name → {site_id, construction_direction}
        site_lookup = {
            s["name"]: {
                "site_id":               s["site_id"],
                "construction_direction": s.get("construction_direction"),
            }
            for s in sites
        }
        print(f"  共 {len(site_lookup)} 个工点")

    # ── 2. 遍历工点文件夹 ────────────────────────────────────────────────────
    site_dirs = sorted([d for d in root.iterdir() if d.is_dir()])
    total_ds = success_ds = skip_ds = fail_ds = 0

    for site_dir in site_dirs:
        # 检查是否含子文件夹（数据类型文件夹）
        type_dirs = [d for d in site_dir.iterdir() if d.is_dir()]
        if not type_dirs:
            print(f"\n[{site_dir.name}] 无子文件夹，跳过")
            continue

        # 读取 config.json 获取工点名称
        cfg_path = site_dir / "config.json"
        if not cfg_path.exists():
            print(f"\n[{site_dir.name}] 无 config.json，跳过")
            continue

        try:
            with cfg_path.open("r", encoding="utf-8") as f:
                cfg = json.load(f)
            site_name: str = cfg.get("name", "").strip()
        except Exception as e:
            print(f"\n[{site_dir.name}] config.json 解析失败: {e}，跳过")
            continue

        if not site_name:
            print(f"\n[{site_dir.name}] config.json 中 name 为空，跳过")
            continue

        # 查找 site_id
        if dry_run:
            site_id = f"DRY-RUN-SITE-{site_dir.name}"
            construction_direction = None
            print(f"\n[{site_dir.name}] {site_name!r}  [DRY-RUN]")
        else:
            site_info = site_lookup.get(site_name)
            if site_info is None:
                print(f"\n[{site_dir.name}] 找不到工点 {site_name!r}，跳过")
                continue
            site_id = site_info["site_id"]
            construction_direction = site_info["construction_direction"]
            print(
                f"\n[{site_dir.name}] {site_name!r}  "
                f"site_id={site_id}  direction={construction_direction}"
            )

        # ── 3. 遍历数据类型文件夹 ────────────────────────────────────────
        for type_dir in sorted(type_dirs):
            dtype = type_dir.name
            data_dirs = sorted([d for d in type_dir.iterdir() if d.is_dir()])
            if not data_dirs:
                continue

            print(f"  [{dtype}]  {len(data_dirs)} 条数据")

            for data_dir in data_dirs:
                total_ds += 1
                ok = process_data_folder(
                    data_folder=data_dir,
                    dtype=dtype,
                    project_id=project_id,
                    site_id=site_id,
                    construction_direction=construction_direction,
                    api_base=api_base,
                    dry_run=dry_run,
                )
                if ok:
                    success_ds += 1
                else:
                    if (data_dir / "index.json").exists():
                        fail_ds += 1
                    else:
                        skip_ds += 1

    print(
        f"\n{'='*60}\n"
        f"完成：共扫描 {total_ds} 个数据文件夹，"
        f"成功 {success_ds}，跳过 {skip_ds}，失败 {fail_ds}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# CLI 入口
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="批量将隧道检测数据文件夹入库（datasets + mileage_extents）"
    )
    parser.add_argument(
        "data_root",
        help="数据根目录（如 E:/Datasets/.../10750）",
    )
    parser.add_argument(
        "project_id",
        help="目标工程 project_id（UUID）",
    )
    parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help=f"API 服务地址（默认 {DEFAULT_API_BASE}）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅解析打印，不实际写库",
    )
    args = parser.parse_args()

    import_all(
        data_root=args.data_root,
        project_id=args.project_id,
        api_base=args.api_base.rstrip("/"),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
