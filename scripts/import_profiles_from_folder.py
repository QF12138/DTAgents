"""
将断面轮廓数据（.stp 文件）批量入库（datasets 表）

参数（位置参数，按顺序输入）：
  1. project_id   工程 UUID
  2. proj_name    工程名称，如 康定隧道
  3. folder       .stp 文件所在文件夹路径

用法示例：
  python import_profiles_from_folder.py <uuid> 康定隧道 E:/.../profiles
  python import_profiles_from_folder.py <uuid> 康定隧道 E:/.../profiles --dry-run
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

import requests

# ──────────────────────────────────────────────────────────────────────────────
# 默认配置
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_API_BASE = "http://localhost:8000"


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
    # 补充其他冠号...
}

# ──────────────────────────────────────────────────────────────────────────────
# 冠号提取
# ──────────────────────────────────────────────────────────────────────────────

def extract_prefix(stem: str) -> str:
    """
    从文件名（去后缀）的最后一个 '-' 之后截取冠号字符串。

    示例：
      "DK278+100-DK"        → "DK"
      "KDTK-PRF-X1DK3+905-X1DK" → "X1DK"
      "profile-H2DK"        → "H2DK"
      "nohyphen"            → ""   （无 '-'，返回空串）
    """
    if "-" not in stem:
        return ""
    return stem.rsplit("-", 1)[-1].strip()


# ──────────────────────────────────────────────────────────────────────────────
# API
# ──────────────────────────────────────────────────────────────────────────────

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

def import_profiles(
    project_id: str,
    proj_name:  str,
    folder:     str,
    api_base:   str,
    dry_run:    bool,
) -> None:
    folder_path = Path(folder).resolve()
    if not folder_path.is_dir():
        print(f"[ERROR] 文件夹不存在: {folder_path}")
        sys.exit(1)

    stp_files = sorted(folder_path.glob("*.stp"))
    if not stp_files:
        print(f"[WARN] 文件夹中未找到 .stp 文件: {folder_path}")
        return

    print(f"共找到 {len(stp_files)} 个 .stp 文件\n")

    success = fail = 0
    for stp_file in stp_files:
        name         = stp_file.stem   # 文件名去掉后缀
        file_size_mb = round(stp_file.stat().st_size / (1024 * 1024), 6)

        # 从文件名最后一个 '-' 后提取冠号，匹配 detail
        prefix = extract_prefix(name)
        detail = PREFIX_DETAIL.get(prefix, prefix) if prefix else ""
        description = f"{proj_name}{detail}断面轮廓"

        payload = {
            "project_id":       project_id,
            "name":             name,
            "data_type":        "PRF",
            "positioning_type": "mileage",
            "file_path":        str(stp_file).replace("\\", "/"),
            "file_format":      "stp",
            "file_size_mb":     file_size_mb,
            "description":      description,
        }

        if dry_run:
            print(
                f"  [DRY-RUN] {name}\n"
                f"            prefix={prefix!r}  detail={detail!r}\n"
                f"            description={description}\n"
                f"            size={file_size_mb} MB\n"
                f"            path={payload['file_path']}"
            )
            success += 1
            continue

        did = post_dataset(api_base, payload)
        if did:
            print(f"  [OK] {name}  → id={did}")
            success += 1
        else:
            print(f"  [FAIL] {name}")
            fail += 1

    print(
        f"\n{'='*60}\n"
        f"完成：共 {len(stp_files)} 个文件，成功 {success}，失败 {fail}"
    )


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="将断面轮廓 .stp 文件批量入库（datasets 表）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
参数说明：
  project_id  工程 UUID
  proj_name   工程名称（如 康定隧道）
  folder      .stp 文件所在文件夹路径

示例：
  python import_profiles_from_folder.py <uuid> 康定隧道 E:/.../profiles
        """,
    )
    parser.add_argument("project_id", help="工程 UUID")
    parser.add_argument("proj_name",  help="工程名称（如 康定隧道）")
    parser.add_argument("folder",     help=".stp 文件所在文件夹路径")
    parser.add_argument(
        "--api-base", default=DEFAULT_API_BASE,
        help=f"API 服务地址（默认 {DEFAULT_API_BASE}）",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="仅解析打印，不实际写库",
    )
    args = parser.parse_args()

    import_profiles(
        project_id = args.project_id,
        proj_name  = args.proj_name,
        folder     = args.folder,
        api_base   = args.api_base.rstrip("/"),
        dry_run    = args.dry_run,
    )


if __name__ == "__main__":
    main()
