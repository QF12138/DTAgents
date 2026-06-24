"""数据管理 REST API - FastAPI (Schema v3)"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent.parent))
from database import db

app = FastAPI(title="DTAgents 数据管理 API", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    return {
        "name": "DTAgents Data API",
        "docs": "/docs",
        "stats": "/api/stats",
        "frontend": "http://127.0.0.1:5173",
    }


@app.on_event("startup")
def startup() -> None:
    db.connect()


@app.on_event("shutdown")
def shutdown() -> None:
    db.close()


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _to_dict(conn, row) -> dict:
    return dict(zip([d[0] for d in conn.description], row))


def _to_list(conn, rows) -> list[dict]:
    cols = [d[0] for d in conn.description]
    return [dict(zip(cols, r)) for r in rows]


def _page(conn, table: str, where: str, params: list, page: int, size: int,
          order: str = "created_at DESC") -> dict:
    total_row = conn.execute(f"SELECT COUNT(*) FROM {table} {where}", params).fetchone()
    total = total_row[0] if total_row else 0
    rows  = conn.execute(
        f"SELECT * FROM {table} {where} ORDER BY {order} LIMIT ? OFFSET ?",
        params + [size, (page - 1) * size],
    ).fetchall()
    return {"total": total, "items": _to_list(conn, rows)}


# ══════════════════════════════════════════════════════════════════════════════
# STATS / DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/stats")
def get_stats():
    c = db.conn
    def cnt(t): return c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    return {
        "projects":           cnt("projects"),
        "work_sites":         cnt("work_sites"),
        "datasets":           cnt("datasets"),
        "processing_history": cnt("processing_history"),
        "model_registry":     cnt("model_registry"),
    }


# ══════════════════════════════════════════════════════════════════════════════
# PROJECTS
# ══════════════════════════════════════════════════════════════════════════════

class ProjectBody(BaseModel):
    name:        str
    type:        Optional[str] = None
    description: Optional[str] = None
    default_crs: Optional[str] = None


@app.get("/api/projects")
def list_projects(
    page: int           = Query(1, ge=1),
    size: int           = Query(20, ge=1, le=100),
    name: Optional[str] = None,
):
    conds, params = [], []
    if name: conds.append("name LIKE ?"); params.append(f"%{name}%")
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return _page(db.conn, "projects", where, params, page, size)


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    row = db.conn.execute("SELECT * FROM projects WHERE project_id=?", [pid]).fetchone()
    if not row: raise HTTPException(404, "工程不存在")
    return _to_dict(db.conn, row)


@app.post("/api/projects", status_code=201)
def create_project(b: ProjectBody):
    pid = str(uuid.uuid4())
    db.conn.execute(
        "INSERT INTO projects (project_id,name,type,description,default_crs) VALUES (?,?,?,?,?)",
        [pid, b.name, b.type, b.description, b.default_crs or "EPSG:4547"],
    )
    return {"project_id": pid}


@app.put("/api/projects/{pid}")
def update_project(pid: str, b: ProjectBody):
    if not db.conn.execute("SELECT project_id FROM projects WHERE project_id=?", [pid]).fetchone():
        raise HTTPException(404, "工程不存在")
    db.conn.execute(
        "UPDATE projects SET name=?,type=?,description=?,default_crs=? WHERE project_id=?",
        [b.name, b.type, b.description, b.default_crs, pid],
    )
    return {"ok": True}


@app.delete("/api/projects/{pid}")
def delete_project(pid: str):
    ref = db.conn.execute("SELECT COUNT(*) FROM work_sites WHERE project_id=?", [pid]).fetchone()[0]
    if ref > 0:
        raise HTTPException(409, f"该工程下还有 {ref} 个工点，请先删除工点")
    db.conn.execute("DELETE FROM projects WHERE project_id=?", [pid])
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# WORK SITES
# ══════════════════════════════════════════════════════════════════════════════

class WorkSiteBody(BaseModel):
    project_id:             str
    name:                   str
    type:                   Optional[str]   = None
    mileage_prefix:         Optional[str]   = None   # 里程冠号，如 X1DK、ZDK
    centerline_id:          Optional[str]   = None   # → datasets.id
    profile_id:             Optional[str]   = None   # → datasets.id
    construction_direction: Optional[str]   = None   # forward | backward
    start_mileage:          Optional[float] = None
    end_mileage:            Optional[float] = None
    description:            Optional[str]   = None


@app.get("/api/work-sites")
def list_work_sites(
    page:       int           = Query(1, ge=1),
    size:       int           = Query(20, ge=1, le=100),
    project_id: Optional[str] = None,
):
    conds, params = [], []
    if project_id: conds.append("project_id = ?"); params.append(project_id)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return _page(db.conn, "work_sites", where, params, page, size, "start_mileage ASC NULLS LAST")


@app.get("/api/work-sites/{wid}")
def get_work_site(wid: str):
    row = db.conn.execute("SELECT * FROM work_sites WHERE site_id=?", [wid]).fetchone()
    if not row: raise HTTPException(404, "工点不存在")
    return _to_dict(db.conn, row)


@app.post("/api/work-sites", status_code=201)
def create_work_site(b: WorkSiteBody):
    # 校验 project_id
    if not db.conn.execute("SELECT project_id FROM projects WHERE project_id=?", [b.project_id]).fetchone():
        raise HTTPException(404, f"工程不存在: {b.project_id}")
    # 校验 centerline_id
    if b.centerline_id and not db.conn.execute("SELECT id FROM datasets WHERE id=?", [b.centerline_id]).fetchone():
        raise HTTPException(404, f"中线数据集不存在: {b.centerline_id}")
    # 校验 profile_id
    if b.profile_id and not db.conn.execute("SELECT id FROM datasets WHERE id=?", [b.profile_id]).fetchone():
        raise HTTPException(404, f"断面轮廓数据集不存在: {b.profile_id}")
    # 里程区间校验
    if b.start_mileage is not None and b.end_mileage is not None and b.start_mileage >= b.end_mileage:
        raise HTTPException(422, "起始里程必须小于终止里程")

    wid = str(uuid.uuid4())
    db.conn.execute(
        """INSERT INTO work_sites
           (site_id,project_id,name,type,mileage_prefix,centerline_id,profile_id,
            construction_direction,start_mileage,end_mileage,description)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        [wid, b.project_id, b.name, b.type, b.mileage_prefix, b.centerline_id, b.profile_id,
         b.construction_direction, b.start_mileage, b.end_mileage, b.description],
    )
    return {"site_id": wid}


def _move_datasets_to_new_site(c, old_site_id: str, new_site_id: str) -> None:
    """将 datasets.site_id 由 old_site_id 改为 new_site_id。

    DuckDB FK 检查基于已提交状态：必须先 COMMIT DELETE，
    FK 约束才真正解除，后续 UPDATE datasets 才能成功。
    """
    dataset_ids = [r[0] for r in c.execute(
        "SELECT id FROM datasets WHERE site_id=?", [old_site_id]
    ).fetchall()]
    if not dataset_ids:
        return

    ph = ",".join("?" * len(dataset_ids))

    # 批量暂存 spatial_extents / mileage_extents
    se_rows = c.execute(
        f"SELECT dataset_id, crs, bbox_minx, bbox_miny, bbox_maxx, bbox_maxy,"
        f"       bbox_minz, bbox_maxz, resolution_m, map_scale"
        f" FROM spatial_extents WHERE dataset_id IN ({ph})", dataset_ids
    ).fetchall()
    me_rows = c.execute(
        f"SELECT dataset_id, start_mileage, end_mileage,"
        f"       offset_lateral, offset_vertical, measurement_dir"
        f" FROM mileage_extents WHERE dataset_id IN ({ph})", dataset_ids
    ).fetchall()

    c.execute("BEGIN")
    # 批量删除后立即 COMMIT，使 FK 约束解除对外可见
    c.execute(f"DELETE FROM spatial_extents WHERE dataset_id IN ({ph})", dataset_ids)
    c.execute(f"DELETE FROM mileage_extents WHERE dataset_id IN ({ph})", dataset_ids)
    c.execute("COMMIT")

    c.execute("BEGIN")
    # 更新 datasets.site_id（FK 约束已解除，安全）
    c.execute("UPDATE datasets SET site_id=? WHERE site_id=?", [new_site_id, old_site_id])

    # 恢复 spatial_extents / mileage_extents
    for row in se_rows:
        c.execute(
            "INSERT INTO spatial_extents"
            " (dataset_id,crs,bbox_minx,bbox_miny,bbox_maxx,bbox_maxy,"
            "  bbox_minz,bbox_maxz,resolution_m,map_scale)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)", list(row)
        )
    for row in me_rows:
        c.execute(
            "INSERT INTO mileage_extents"
            " (dataset_id,start_mileage,end_mileage,"
            "  offset_lateral,offset_vertical,measurement_dir)"
            " VALUES (?,?,?,?,?,?)", list(row)
        )
    c.execute("COMMIT")

@app.put("/api/work-sites/{wid}")
def update_work_site(wid: str, b: WorkSiteBody):
    orig = db.conn.execute(
        "SELECT created_at FROM work_sites WHERE site_id=?", [wid]
    ).fetchone()
    if not orig:
        raise HTTPException(404, "工点不存在")
    if b.centerline_id and not db.conn.execute("SELECT id FROM datasets WHERE id=?", [b.centerline_id]).fetchone():
        raise HTTPException(404, f"中线数据集不存在: {b.centerline_id}")
    if b.profile_id and not db.conn.execute("SELECT id FROM datasets WHERE id=?", [b.profile_id]).fetchone():
        raise HTTPException(404, f"断面轮廓数据集不存在: {b.profile_id}")
    if b.start_mileage is not None and b.end_mileage is not None and b.start_mileage >= b.end_mileage:
        raise HTTPException(422, "起始里程必须小于终止里程")

    # DuckDB FK 检查基于已提交状态，故每个阶段独立提交：
    #   Step 1: 插入新 site_id 行（保留 created_at）并提交
    #   Step 2: 迁移 datasets（内部自行 COMMIT）、processing_history、model_registry
    #   Step 3: 删除旧行并提交

    new_site_id = str(uuid.uuid4())
    created_at  = orig[0]
    _fields = [b.project_id, b.name, b.type, b.mileage_prefix,
               b.centerline_id, b.profile_id, b.construction_direction,
               b.start_mileage, b.end_mileage, b.description]

    c = db.conn
    try:
        # Step 1
        c.execute("BEGIN")
        c.execute("""
            INSERT INTO work_sites
                (site_id, project_id, name, type, mileage_prefix,
                 centerline_id, profile_id, construction_direction,
                 start_mileage, end_mileage, description, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, [new_site_id] + _fields + [created_at])
        c.execute("COMMIT")

        # Step 2（_move_datasets_to_new_site 内部自行 COMMIT）
        _move_datasets_to_new_site(c, wid, new_site_id)
        c.execute("UPDATE processing_history SET site_id=? WHERE site_id=?", [new_site_id, wid])
        c.execute("UPDATE model_registry     SET site_id=? WHERE site_id=?", [new_site_id, wid])

        # Step 3
        c.execute("BEGIN")
        c.execute("DELETE FROM work_sites WHERE site_id=?", [wid])
        c.execute("COMMIT")

    except Exception as e:
        try:
            c.execute("ROLLBACK")
        except Exception:
            pass
        raise HTTPException(500, f"更新工点失败: {e}")

    return {"ok": True, "site_id": new_site_id}


@app.delete("/api/work-sites/{wid}")
def delete_work_site(wid: str):
    ds_ref  = db.conn.execute("SELECT COUNT(*) FROM datasets           WHERE site_id=?", [wid]).fetchone()[0]
    ph_ref  = db.conn.execute("SELECT COUNT(*) FROM processing_history WHERE site_id=?", [wid]).fetchone()[0]
    mr_ref  = db.conn.execute("SELECT COUNT(*) FROM model_registry     WHERE site_id=?", [wid]).fetchone()[0]
    if ds_ref > 0:
        raise HTTPException(409, f"该工点下还有 {ds_ref} 个数据集，请先删除数据集")
    if ph_ref > 0:
        raise HTTPException(409, f"该工点下还有 {ph_ref} 条处理记录，请先删除处理记录")
    if mr_ref > 0:
        raise HTTPException(409, f"该工点下还有 {mr_ref} 个模型，请先删除模型")
    db.conn.execute("DELETE FROM work_sites WHERE site_id=?", [wid])
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# DATASETS
# ══════════════════════════════════════════════════════════════════════════════

class DatasetBody(BaseModel):
    project_id:        Optional[str]       = None
    site_id:           Optional[str]       = None
    name:              str
    data_type:         str
    positioning_type:  str                 = "spatial"
    file_path:         str
    file_format:       Optional[str]       = None
    file_size_mb:      Optional[float]     = None
    checksum:          Optional[str]       = None
    survey_date_start: Optional[str]       = None
    survey_date_end:   Optional[str]       = None
    status:            str                 = "raw"
    quality_flag:      int                 = 0
    tags:              Optional[list[str]] = None
    description:       Optional[str]       = None
    extra_meta:        Optional[dict]      = None
    # 空间范围子对象（positioning_type 含 spatial 时使用）
    spatial:           Optional[dict]      = None
    # 里程范围子对象（positioning_type 含 mileage 时使用）
    mileage:           Optional[dict]      = None


@app.get("/api/datasets")
def list_datasets(
    page:             int           = Query(1, ge=1),
    size:             int           = Query(20, ge=1, le=200),
    data_type:        Optional[str] = None,
    status:           Optional[str] = None,
    name:             Optional[str] = None,
    project_id:       Optional[str] = None,
    site_id:          Optional[str] = None,
    positioning_type: Optional[str] = None,
):
    conds, params = [], []
    if data_type:        conds.append("data_type = ?");        params.append(data_type)
    if status:           conds.append("status = ?");           params.append(status)
    if name:             conds.append("name LIKE ?");          params.append(f"%{name}%")
    if project_id:       conds.append("project_id = ?");       params.append(project_id)
    if site_id:          conds.append("site_id = ?");          params.append(site_id)
    if positioning_type: conds.append("positioning_type = ?"); params.append(positioning_type)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return _page(db.conn, "datasets", where, params, page, size)


@app.get("/api/datasets/{did}")
def get_dataset(did: str):
    row = db.conn.execute(
        """SELECT d.*,
                  s.crs              AS s_crs,
                  s.bbox_minx        AS s_bbox_minx,   s.bbox_miny   AS s_bbox_miny,
                  s.bbox_maxx        AS s_bbox_maxx,   s.bbox_maxy   AS s_bbox_maxy,
                  s.bbox_minz        AS s_bbox_minz,   s.bbox_maxz   AS s_bbox_maxz,
                  s.resolution_m     AS s_resolution_m, s.map_scale  AS s_map_scale,
                  m.start_mileage    AS m_start_mileage,
                  m.end_mileage      AS m_end_mileage,
                  m.offset_lateral   AS m_offset_lateral,
                  m.offset_vertical  AS m_offset_vertical,
                  m.measurement_dir  AS m_measurement_dir
           FROM datasets d
           LEFT JOIN spatial_extents s ON s.dataset_id = d.id
           LEFT JOIN mileage_extents m ON m.dataset_id = d.id
           WHERE d.id = ?""",
        [did],
    ).fetchone()
    if not row: raise HTTPException(404, "数据集不存在")
    return _to_dict(db.conn, row)


@app.post("/api/datasets", status_code=201)
def create_dataset(b: DatasetBody):
    did = str(uuid.uuid4())
    c = db.conn
    try:
        c.execute("BEGIN")
        c.execute(
            """INSERT INTO datasets
               (id,project_id,site_id,name,data_type,positioning_type,file_path,file_format,
                file_size_mb,checksum,survey_date_start,survey_date_end,
                status,quality_flag,tags,description,extra_meta)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [did, b.project_id, b.site_id, b.name, b.data_type, b.positioning_type,
             b.file_path, b.file_format, b.file_size_mb, b.checksum,
             b.survey_date_start, b.survey_date_end, b.status, b.quality_flag,
             json.dumps(b.tags) if b.tags else None,
             b.description,
             json.dumps(b.extra_meta) if b.extra_meta else None],
        )
        if b.spatial:
            s = b.spatial
            c.execute(
                """INSERT INTO spatial_extents
                   (dataset_id,crs,bbox_minx,bbox_miny,bbox_maxx,bbox_maxy,
                    bbox_minz,bbox_maxz,resolution_m,map_scale)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                [did, s.get("crs"), s.get("bbox_minx"), s.get("bbox_miny"),
                 s.get("bbox_maxx"), s.get("bbox_maxy"),
                 s.get("bbox_minz"), s.get("bbox_maxz"),
                 s.get("resolution_m"), s.get("map_scale")],
            )
        if b.mileage:
            m = b.mileage
            c.execute(
                """INSERT INTO mileage_extents
                   (dataset_id,start_mileage,end_mileage,
                    offset_lateral,offset_vertical,measurement_dir)
                   VALUES (?,?,?,?,?,?)""",
                [did, m.get("start_mileage"), m.get("end_mileage"),
                 m.get("offset_lateral", 0), m.get("offset_vertical", 0),
                 m.get("measurement_dir")],
            )
        c.execute("COMMIT")
    except Exception as e:
        c.execute("ROLLBACK")
        raise HTTPException(500, f"创建失败: {e}")
    return {"id": did}


@app.put("/api/datasets/{did}")
def update_dataset(did: str, b: DatasetBody):
    if not db.conn.execute("SELECT id FROM datasets WHERE id=?", [did]).fetchone():
        raise HTTPException(404, "数据集不存在")
    c = db.conn
    try:
        # 先删除子表记录（绕过 FK 重校验问题）
        c.execute("BEGIN")
        c.execute("DELETE FROM spatial_extents WHERE dataset_id=?", [did])
        c.execute("DELETE FROM mileage_extents WHERE dataset_id=?", [did])
        c.execute("COMMIT")

        c.execute("BEGIN")
        c.execute(
            """UPDATE datasets SET
               project_id=?,site_id=?,name=?,data_type=?,positioning_type=?,
               file_path=?,file_format=?,file_size_mb=?,checksum=?,
               survey_date_start=?,survey_date_end=?,status=?,quality_flag=?,
               tags=?,description=?,extra_meta=?,updated_at=current_timestamp
               WHERE id=?""",
            [b.project_id, b.site_id, b.name, b.data_type, b.positioning_type,
             b.file_path, b.file_format, b.file_size_mb, b.checksum,
             b.survey_date_start, b.survey_date_end, b.status, b.quality_flag,
             json.dumps(b.tags) if b.tags else None,
             b.description,
             json.dumps(b.extra_meta) if b.extra_meta else None,
             did],
        )
        if b.spatial:
            s = b.spatial
            c.execute(
                """INSERT INTO spatial_extents
                   (dataset_id,crs,bbox_minx,bbox_miny,bbox_maxx,bbox_maxy,
                    bbox_minz,bbox_maxz,resolution_m,map_scale)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                [did, s.get("crs"), s.get("bbox_minx"), s.get("bbox_miny"),
                 s.get("bbox_maxx"), s.get("bbox_maxy"),
                 s.get("bbox_minz"), s.get("bbox_maxz"),
                 s.get("resolution_m"), s.get("map_scale")],
            )
        if b.mileage:
            m = b.mileage
            c.execute(
                """INSERT INTO mileage_extents
                   (dataset_id,start_mileage,end_mileage,
                    offset_lateral,offset_vertical,measurement_dir)
                   VALUES (?,?,?,?,?,?)""",
                [did, m.get("start_mileage"), m.get("end_mileage"),
                 m.get("offset_lateral", 0), m.get("offset_vertical", 0),
                 m.get("measurement_dir")],
            )
        c.execute("COMMIT")
    except Exception as e:
        c.execute("ROLLBACK")
        raise HTTPException(500, f"更新失败: {e}")
    return {"ok": True}


@app.delete("/api/datasets/{did}")
def delete_dataset(did: str):
    c = db.conn
    c.execute("DELETE FROM spatial_extents WHERE dataset_id=?", [did])
    c.execute("DELETE FROM mileage_extents WHERE dataset_id=?", [did])
    c.execute("DELETE FROM datasets WHERE id=?", [did])
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# PROCESSING HISTORY
# ══════════════════════════════════════════════════════════════════════════════

@app.get("/api/history")
def list_history(
    page:       int           = Query(1, ge=1),
    size:       int           = Query(20, ge=1, le=100),
    status:     Optional[str] = None,
    agent_name: Optional[str] = None,
    project_id: Optional[str] = None,
    site_id:    Optional[str] = None,
):
    conds, params = [], []
    if status:     conds.append("status = ?");        params.append(status)
    if agent_name: conds.append("agent_name LIKE ?"); params.append(f"%{agent_name}%")
    if project_id: conds.append("project_id = ?");    params.append(project_id)
    if site_id:    conds.append("site_id = ?");        params.append(site_id)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return _page(db.conn, "processing_history", where, params, page, size)


@app.delete("/api/history/{hid}")
def delete_history(hid: int):
    db.conn.execute("DELETE FROM processing_history WHERE id=?", [hid])
    return {"ok": True}


# ══════════════════════════════════════════════════════════════════════════════
# MODEL REGISTRY
# ══════════════════════════════════════════════════════════════════════════════

class ModelBody(BaseModel):
    name:              str
    description:       Optional[str]       = None
    project_id:        Optional[str]       = None
    site_id:           Optional[str]       = None
    positioning_type:  str                 = "spatial"
    # 空间定位
    crs_epsg:          Optional[int]       = None
    bbox_minx:         Optional[float]     = None
    bbox_miny:         Optional[float]     = None
    bbox_minz:         Optional[float]     = None
    bbox_maxx:         Optional[float]     = None
    bbox_maxy:         Optional[float]     = None
    bbox_maxz:         Optional[float]     = None
    # 里程定位（centerline_id → datasets.id）
    centerline_id:     Optional[str]       = None
    start_mileage:     Optional[float]     = None
    end_mileage:       Optional[float]     = None
    model_radius:      Optional[float]     = None
    # 网格参数
    voxel_resolution:  Optional[float]     = None
    grid_nx:           Optional[int]       = None
    grid_ny:           Optional[int]       = None
    grid_nz:           Optional[int]       = None
    # 文件
    file_path:         Optional[str]       = None
    file_format:       Optional[str]       = None
    file_size_mb:      Optional[float]     = None
    attributes:        Optional[list[str]] = None
    input_dataset_ids: Optional[list[str]] = None
    processing_ids:    Optional[list[int]] = None
    version:           int                 = 1


@app.get("/api/models")
def list_models(
    page:             int           = Query(1, ge=1),
    size:             int           = Query(20, ge=1, le=100),
    name:             Optional[str] = None,
    project_id:       Optional[str] = None,
    site_id:          Optional[str] = None,
    positioning_type: Optional[str] = None,
):
    conds, params = [], []
    if name:             conds.append("name LIKE ?");          params.append(f"%{name}%")
    if project_id:       conds.append("project_id = ?");       params.append(project_id)
    if site_id:          conds.append("site_id = ?");          params.append(site_id)
    if positioning_type: conds.append("positioning_type = ?"); params.append(positioning_type)
    where = ("WHERE " + " AND ".join(conds)) if conds else ""
    return _page(db.conn, "model_registry", where, params, page, size)


@app.get("/api/models/{mid}")
def get_model(mid: str):
    row = db.conn.execute("SELECT * FROM model_registry WHERE id=?", [mid]).fetchone()
    if not row: raise HTTPException(404, "模型不存在")
    return _to_dict(db.conn, row)


@app.post("/api/models", status_code=201)
def create_model(b: ModelBody):
    mid = str(uuid.uuid4())
    db.conn.execute(
        """INSERT INTO model_registry
           (id,name,description,project_id,site_id,positioning_type,
            crs_epsg,bbox_minx,bbox_miny,bbox_minz,bbox_maxx,bbox_maxy,bbox_maxz,
            centerline_id,start_mileage,end_mileage,model_radius,
            voxel_resolution,grid_nx,grid_ny,grid_nz,
            file_path,file_format,file_size_mb,
            attributes,input_dataset_ids,processing_ids,version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        [mid, b.name, b.description, b.project_id, b.site_id, b.positioning_type,
         b.crs_epsg, b.bbox_minx, b.bbox_miny, b.bbox_minz,
         b.bbox_maxx, b.bbox_maxy, b.bbox_maxz,
         b.centerline_id, b.start_mileage, b.end_mileage, b.model_radius,
         b.voxel_resolution, b.grid_nx, b.grid_ny, b.grid_nz,
         b.file_path, b.file_format, b.file_size_mb,
         json.dumps(b.attributes)        if b.attributes        else None,
         json.dumps(b.input_dataset_ids) if b.input_dataset_ids else None,
         json.dumps(b.processing_ids)    if b.processing_ids    else None,
         b.version],
    )
    return {"id": mid}


@app.put("/api/models/{mid}")
def update_model(mid: str, b: ModelBody):
    if not db.conn.execute("SELECT id FROM model_registry WHERE id=?", [mid]).fetchone():
        raise HTTPException(404, "模型不存在")
    db.conn.execute(
        """UPDATE model_registry SET
           name=?,description=?,project_id=?,site_id=?,positioning_type=?,
           crs_epsg=?,bbox_minx=?,bbox_miny=?,bbox_minz=?,bbox_maxx=?,bbox_maxy=?,bbox_maxz=?,
           centerline_id=?,start_mileage=?,end_mileage=?,model_radius=?,
           voxel_resolution=?,grid_nx=?,grid_ny=?,grid_nz=?,
           file_path=?,file_format=?,file_size_mb=?,
           attributes=?,input_dataset_ids=?,processing_ids=?,version=?
           WHERE id=?""",
        [b.name, b.description, b.project_id, b.site_id, b.positioning_type,
         b.crs_epsg, b.bbox_minx, b.bbox_miny, b.bbox_minz,
         b.bbox_maxx, b.bbox_maxy, b.bbox_maxz,
         b.centerline_id, b.start_mileage, b.end_mileage, b.model_radius,
         b.voxel_resolution, b.grid_nx, b.grid_ny, b.grid_nz,
         b.file_path, b.file_format, b.file_size_mb,
         json.dumps(b.attributes)        if b.attributes        else None,
         json.dumps(b.input_dataset_ids) if b.input_dataset_ids else None,
         json.dumps(b.processing_ids)    if b.processing_ids    else None,
         b.version, mid],
    )
    return {"ok": True}


@app.delete("/api/models/{mid}")
def delete_model(mid: str):
    db.conn.execute("DELETE FROM model_registry WHERE id=?", [mid])
    return {"ok": True}



# python -m uvicorn api.server:app --reload --port 8000
