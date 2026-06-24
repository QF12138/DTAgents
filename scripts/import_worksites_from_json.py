"""
从隧道施工管理系统导出的 config.json 解析工点数据并通过 API 入库或更新。

字段映射：
  JSON.name            → work_sites.name
  JSON.gdTypeStr       → work_sites.type       （过滤：跳过横通道、救援通道）
  JSON.startMilestone  → work_sites.start_mileage  （/ 10）
  JSON.endMilestone    → work_sites.end_mileage    （/ 10）
  里程差正负             → work_sites.construction_direction  （forward / backward）
  JSON.startPrefix     → work_sites.mileage_prefix（直接写入）
                       → work_sites.centerline_id / profile_id  （按前缀字典映射）
  statusFlagStr + jdAlertStr → work_sites.description

运行模式：
  默认（无 --update）：POST 新建工点
  --update            ：按名称查找已有工点，PUT 更新（site_id 不变），用于补填新增字段
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

import requests

# ──────────────────────────────────────────────────────────────────────────────
# 配置
# ──────────────────────────────────────────────────────────────────────────────

API_BASE = "http://localhost:8000"   # 修改为实际服务地址

# 需要跳过的工点类型（gdTypeStr）
SKIP_TYPES: set[str] = {"横通道", "救援通道", "救援平导", "排烟通道", "横跨救援通道"}

# startPrefix → (centerline_id, profile_id)
PREFIX_TO_IDS: dict[str, tuple[Optional[str], Optional[str]]] = {
    "D3K":  ("6e2c378b-c06b-4cd4-85e6-5e2702cb7d11", "1d67204e-bc9d-4d2f-8ea5-83867105212d"),
    "D4K":  ("6e2c378b-c06b-4cd4-85e6-5e2702cb7d11", "1d67204e-bc9d-4d2f-8ea5-83867105212d"),
    "DK":  ("6e2c378b-c06b-4cd4-85e6-5e2702cb7d11", "1d67204e-bc9d-4d2f-8ea5-83867105212d"),
    "PDK":  ("74092696-35c0-4a17-98d0-89dbed732629", "8242959e-a1f3-48e8-ada8-703cfacf215f"),
    "H1DK":  ("ef868382-000b-430b-80b3-7f1facc53920", "0ceeb143-38cb-4eb9-9e81-717edbc47383"),
    "X1DK":  ("70a5ae96-f18f-46c0-9a7d-755e02578925", "8011a67b-6929-4a34-840f-b4c2d878656e"),
    "X2DK":  ("b2ec83ec-8c74-4145-9b6f-a76ac2a755b9", "cce75b85-6d81-48b2-a1fb-90454b04e320"),
}

# ──────────────────────────────────────────────────────────────────────────────
# 解析
# ──────────────────────────────────────────────────────────────────────────────

def parse_entry(entry: dict) -> Optional[dict]:
    """将单条 JSON 记录转换为 WorkSiteBody 字典，无法解析时返回 None。"""

    gd_type_str: str = entry.get("gdTypeStr", "")

    # 过滤不需要的类型
    if gd_type_str in SKIP_TYPES:
        return None

    name: str = entry.get("name", "").strip()
    if not name:
        return None

    # 里程换算（原始值 / 10）
    raw_start = entry.get("startMilestone")
    raw_end   = entry.get("endMilestone")

    start_mileage: Optional[float] = raw_start / 10.0 if raw_start is not None else None
    end_mileage:   Optional[float] = raw_end   / 10.0 if raw_end   is not None else None

    # 施工推进方向：start > end → backward（向小里程掘进），否则 forward
    construction_direction: Optional[str] = None
    if start_mileage is not None and end_mileage is not None:
        construction_direction = "backward" if start_mileage > end_mileage else "forward"

    # 注意：server.py 要求 start_mileage < end_mileage，需将二者排序存入
    if start_mileage is not None and end_mileage is not None:
        db_start = min(start_mileage, end_mileage)
        db_end   = max(start_mileage, end_mileage)
    else:
        db_start, db_end = start_mileage, end_mileage

    # centerline_id / profile_id
    prefix: str = entry.get("startPrefix", "")
    centerline_id, profile_id = PREFIX_TO_IDS.get(prefix, (None, None))

    # type
    site_type = gd_type_str

    # description
    status_flag_str: str = entry.get("statusFlagStr", "") or ""
    jd_alert_str:    str = entry.get("jdAlertStr",    "") or ""
    parts = [s for s in [status_flag_str, jd_alert_str] if s]
    description = " | ".join(parts) if parts else None

    return {
        "name":                   name,
        "type":                   site_type,
        "mileage_prefix":         prefix if prefix else None,
        "start_mileage":          db_start,
        "end_mileage":            db_end,
        "construction_direction": construction_direction,
        "centerline_id":          centerline_id,
        "profile_id":             profile_id,
        "description":            description,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 入库
# ──────────────────────────────────────────────────────────────────────────────

def fetch_all_sites(project_id: str, api_base: str) -> dict[str, dict]:
    """从 API 拉取该 project_id 下所有工点，返回 {name: site_record} 字典。"""
    name_to_site: dict[str, dict] = {}
    page = 1
    while True:
        resp = requests.get(
            f"{api_base}/api/work-sites",
            params={"project_id": project_id, "page": page, "size": 100},
            timeout=10,
        )
        resp.raise_for_status()
        payload = resp.json()
        items = payload.get("items", [])
        for s in items:
            name_to_site[s["name"]] = s
        if page >= payload.get("pages", 1):
            break
        page += 1
    return name_to_site


def import_json(
    json_path: str,
    project_id: str,
    api_base: str,
    dry_run: bool = False,
    update: bool = False,
) -> None:
    path = Path(json_path)
    if not path.exists():
        print(f"[ERROR] 文件不存在: {path}")
        sys.exit(1)

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        print("[ERROR] JSON 顶层应为数组")
        sys.exit(1)

    # --update 模式：预先拉取已有工点索引（按名称）
    existing: dict[str, dict] = {}
    if update and not dry_run:
        print("正在获取已有工点列表…")
        existing = fetch_all_sites(project_id, api_base)
        print(f"  已找到 {len(existing)} 个工点\n")

    total = len(data)
    skipped = 0
    success = 0
    failed  = 0
    not_found = 0

    for i, entry in enumerate(data):
        site_body = parse_entry(entry)

        if site_body is None:
            skipped += 1
            gd_type = entry.get("gdTypeStr", "?")
            name    = entry.get("name", "?")
            print(f"  [{i+1}/{total}] 跳过  {name!r}  (type={gd_type})")
            continue

        site_body["project_id"] = project_id
        name = site_body["name"]

        if dry_run:
            mode = "UPDATE" if update else "CREATE"
            print(f"  [{i+1}/{total}] [DRY-RUN/{mode}] {name!r}  →  {site_body}")
            success += 1
            continue

        if update:
            # 按名称查找已有工点
            existing_site = existing.get(name)
            if existing_site is None:
                print(f"  [{i+1}/{total}] NOT FOUND  {name!r}  （库中无此工点，跳过）")
                not_found += 1
                continue
            site_id = existing_site["site_id"]
            try:
                resp = requests.put(
                    f"{api_base}/api/work-sites/{site_id}",
                    json=site_body,
                    timeout=10,
                )
                if resp.status_code == 200:
                    print(
                        f"  [{i+1}/{total}] UPDATED  {name!r}"
                        f"  mileage_prefix={site_body.get('mileage_prefix')!r}"
                        f"  site_id={site_id}"
                    )
                    success += 1
                else:
                    print(
                        f"  [{i+1}/{total}] FAIL  {name!r}  "
                        f"HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                    failed += 1
            except requests.RequestException as e:
                print(f"  [{i+1}/{total}] ERROR  {name!r}  {e}")
                failed += 1
        else:
            try:
                resp = requests.post(
                    f"{api_base}/api/work-sites",
                    json=site_body,
                    timeout=10,
                )
                if resp.status_code == 201:
                    site_id = resp.json().get("site_id", "?")
                    print(f"  [{i+1}/{total}] OK  {name!r}  →  site_id={site_id}")
                    success += 1
                else:
                    print(
                        f"  [{i+1}/{total}] FAIL  {name!r}  "
                        f"HTTP {resp.status_code}: {resp.text[:200]}"
                    )
                    failed += 1
            except requests.RequestException as e:
                print(f"  [{i+1}/{total}] ERROR  {name!r}  {e}")
                failed += 1

    summary = f"\n完成：共 {total} 条，成功 {success}，跳过 {skipped}，失败 {failed}"
    if update:
        summary += f"，库中未找到 {not_found}"
    print(summary)


# ──────────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="将隧道施工管理系统 config.json 导入 DTAgents work_sites 表"
    )
    parser.add_argument("json_path",   help="config.json 文件路径")
    parser.add_argument("project_id",  help="目标工程 project_id（UUID）")
    parser.add_argument("--api-base", default=API_BASE, help=f"API 服务地址（默认 {API_BASE}）")
    parser.add_argument("--dry-run", action="store_true", help="仅解析打印，不实际写库")
    parser.add_argument(
        "--update",
        action="store_true",
        help="更新模式：按名称匹配已有工点并 PUT 更新（site_id 不变），用于补填 mileage_prefix 等新增字段",
    )
    args = parser.parse_args()

    import_json(args.json_path, args.project_id, args.api_base, dry_run=args.dry_run, update=args.update)


if __name__ == "__main__":
    main()
