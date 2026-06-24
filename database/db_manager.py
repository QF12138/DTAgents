"""数据库连接管理 - DuckDB 单例连接器（Schema v3）"""
from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator, Optional

import duckdb

from config import DB_PATH
from .models import (
    Project, WorkSite,
    Dataset, SpatialExtent, MileageExtent,
    ProcessingHistory, ModelRegistry,
)


class DBManager:
    """DuckDB 连接管理器（单实例，线程安全通过单连接序列化）。"""

    _instance: Optional["DBManager"] = None

    def __new__(cls) -> "DBManager":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._conn = None
        return cls._instance

    # ──────────────────────────────────────────────
    # 连接管理
    # ──────────────────────────────────────────────
    def connect(self) -> None:
        """初始化数据库连接并建表。"""
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(DB_PATH))
        self._init_schema()

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self.connect()
        return self._conn

    @contextmanager
    def transaction(self) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        """简单事务上下文管理器。"""
        self.conn.begin()
        try:
            yield self.conn
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def _init_schema(self) -> None:
        schema_path = Path(__file__).parent / "schema.sql"
        sql = schema_path.read_text(encoding="utf-8-sig")  # utf-8-sig 自动去除 BOM
        for stmt in sql.split(";"):
            cleaned = stmt.strip()
            has_sql = any(
                line.strip() and not line.strip().startswith("--")
                for line in cleaned.splitlines()
            )
            if has_sql:
                try:
                    self.conn.execute(cleaned)
                except Exception as exc:
                    raise RuntimeError(
                        f"Schema 初始化失败，执行语句：\n{cleaned}\n错误：{exc}"
                    ) from exc

    # ──────────────────────────────────────────────
    # 内部工具
    # ──────────────────────────────────────────────
    def _fetchall(self, sql: str, params: list[Any] | None = None) -> list[dict[str, Any]]:
        rows = self.conn.execute(sql, params or []).fetchall()
        cols = [d[0] for d in self.conn.description]
        return [dict(zip(cols, r)) for r in rows]

    def _fetchone(self, sql: str, params: list[Any] | None = None) -> Optional[dict[str, Any]]:
        row = self.conn.execute(sql, params or []).fetchone()
        if row is None:
            return None
        cols = [d[0] for d in self.conn.description]
        return dict(zip(cols, row))

    # ──────────────────────────────────────────────
    # projects 表操作
    # ──────────────────────────────────────────────
    def insert_project(self, project: Project) -> str:
        self.conn.execute(
            """
            INSERT INTO projects (project_id, name, type, description, default_crs)
            VALUES (?, ?, ?, ?, ?)
            """,
            [project.project_id, project.name, project.type,
             project.description, project.default_crs],
        )
        return project.project_id

    def get_project(self, project_id: str) -> Optional[dict[str, Any]]:
        return self._fetchone("SELECT * FROM projects WHERE project_id = ?", [project_id])

    def list_projects(self) -> list[dict[str, Any]]:
        return self._fetchall("SELECT * FROM projects ORDER BY created_at DESC")

    # ──────────────────────────────────────────────
    # work_sites 表操作
    # ──────────────────────────────────────────────
    def insert_work_site(self, site: WorkSite) -> str:
        self.conn.execute(
            """
            INSERT INTO work_sites (
                site_id, project_id, name, type,
                mileage_prefix,
                centerline_id, profile_id,
                construction_direction,
                start_mileage, end_mileage, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [site.site_id, site.project_id, site.name, site.type,
             site.mileage_prefix,
             site.centerline_id, site.profile_id,
             site.construction_direction,
             site.start_mileage, site.end_mileage, site.description],
        )
        return site.site_id

    def get_work_site(self, site_id: str) -> Optional[dict[str, Any]]:
        return self._fetchone("SELECT * FROM work_sites WHERE site_id = ?", [site_id])

    def list_work_sites(
        self,
        project_id: Optional[str] = None,
        mileage_prefix: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        conditions, params = [], []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if mileage_prefix:
            conditions.append("mileage_prefix = ?")
            params.append(mileage_prefix)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        return self._fetchall(
            f"SELECT * FROM work_sites {where} ORDER BY start_mileage", params
        )

    def get_work_sites_by_ids(self, site_ids: list[str]) -> list[dict[str, Any]]:
        """批量查询工点的中线/纵断面辅助数据 ID。"""
        if not site_ids:
            return []
        placeholders = ", ".join(["?"] * len(site_ids))
        return self._fetchall(
            f"SELECT site_id, centerline_id, profile_id FROM work_sites WHERE site_id IN ({placeholders})",
            site_ids,
        )

    # ──────────────────────────────────────────────
    # datasets 表操作
    # ──────────────────────────────────────────────
    def insert_dataset(self, ds: Dataset) -> str:
        """注册数据集基础信息，返回 ID。定位扩展信息通过
        insert_spatial_extent / insert_mileage_extent 单独写入。"""
        self.conn.execute(
            """
            INSERT INTO datasets (
                id, project_id, site_id, name, data_type, positioning_type,
                file_path, file_format, file_size_mb, checksum,
                survey_date_start, survey_date_end,
                status, quality_flag, tags, description, extra_meta
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ds.id, ds.project_id, ds.site_id,
                ds.name, ds.data_type, ds.positioning_type,
                ds.file_path, ds.file_format, ds.file_size_mb, ds.checksum,
                ds.survey_date_start, ds.survey_date_end,
                ds.status, ds.quality_flag,
                json.dumps(ds.tags) if ds.tags else None,
                ds.description,
                json.dumps(ds.extra_meta) if ds.extra_meta else None,
            ],
        )
        return ds.id

    def get_dataset(self, dataset_id: str) -> Optional[dict[str, Any]]:
        """查询数据集基础信息（不含定位扩展）。"""
        return self._fetchone("SELECT * FROM datasets WHERE id = ?", [dataset_id])

    def get_dataset_full(self, dataset_id: str) -> Optional[dict[str, Any]]:
        """查询数据集及其定位扩展信息（LEFT JOIN 两张扩展表）。"""
        return self._fetchone(
            """
            SELECT d.*,
                   se.crs, se.bbox_minx, se.bbox_miny, se.bbox_maxx, se.bbox_maxy,
                   se.bbox_minz, se.bbox_maxz, se.resolution_m, se.map_scale,
                   me.start_mileage, me.end_mileage,
                   me.offset_lateral, me.offset_vertical,
                   me.measurement_dir
            FROM datasets d
            LEFT JOIN spatial_extents se ON d.id = se.dataset_id
            LEFT JOIN mileage_extents me ON d.id = me.dataset_id
            WHERE d.id = ?
            """,
            [dataset_id],
        )

    def query_datasets(
        self,
        project_id: Optional[str] = None,
        site_ids: Optional[list[str]] = None,
        data_type: Optional[str] = None,
        mileage_range: Optional[list[float]] = None,  # [start_m, end_m]
        time_range: Optional[list[str]] = None,        # [start_iso, end_iso]
    ) -> list[dict[str, Any]]:
        """多条件查询数据集列表（含里程扩展信息）。"""
        conditions: list[str] = []
        params: list[Any] = []

        if project_id:
            conditions.append("d.project_id = ?")
            params.append(project_id)
        if site_ids:
            placeholders = ", ".join(["?"] * len(site_ids))
            conditions.append(f"d.site_id IN ({placeholders})")
            params.extend(site_ids)
        if data_type:
            conditions.append("d.data_type = ?")
            params.append(data_type)
        if mileage_range:
            start, end = mileage_range
            conditions.append(
                "me.start_mileage <= ? AND (me.end_mileage IS NULL OR me.end_mileage >= ?)"
            )
            params.extend([end, start])
        if time_range and len(time_range) == 2:
            t_start, t_end = time_range
            conditions.append(
                "(d.survey_date_end IS NULL OR d.survey_date_end >= ?) AND "
                "(d.survey_date_start IS NULL OR d.survey_date_start <= ?)"
            )
            params.extend([t_start, t_end])

        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        return self._fetchall(
            f"""
            SELECT d.id, d.name, d.data_type, d.site_id, d.project_id,
                   d.file_path, d.file_format, d.description,
                   d.survey_date_start, d.survey_date_end,
                   me.start_mileage, me.end_mileage
            FROM datasets d
            LEFT JOIN mileage_extents me ON d.id = me.dataset_id
            {where}
            ORDER BY d.data_type, me.start_mileage, d.created_at DESC
            """,
            params,
        )

    def update_dataset_status(
        self, dataset_id: str, status: str, quality_flag: Optional[int] = None
    ) -> None:
        
        spatial_ext = self._fetchone("SELECT * FROM spatial_extents WHERE dataset_id = ?", [dataset_id])
        mileage_ext = self._fetchone("SELECT * FROM mileage_extents WHERE dataset_id = ?", [dataset_id])

        if spatial_ext:
            self.conn.execute("DELETE FROM spatial_extents WHERE dataset_id = ?", [dataset_id])
        if mileage_ext:
            self.conn.execute("DELETE FROM mileage_extents WHERE dataset_id = ?", [dataset_id])
        
        if quality_flag is not None:
            self.conn.execute(
                "UPDATE datasets SET status=?, quality_flag=?, updated_at=current_timestamp WHERE id=?",
                [status, quality_flag, dataset_id],
            )
        else:
            self.conn.execute(
                "UPDATE datasets SET status=?, updated_at=current_timestamp WHERE id=?",
                [status, dataset_id],
            )

        if spatial_ext:
            s_cols = list(spatial_ext.keys())
            s_vals = list(spatial_ext.values())
            s_placeholders = ", ".join(["?"] * len(spatial_ext))
            self.conn.execute(
                f"INSERT INTO spatial_extents ({', '.join(s_cols)}) VALUES ({s_placeholders})", 
                s_vals
            )

        if mileage_ext:
            m_cols = list(mileage_ext.keys())
            m_vals = list(mileage_ext.values())
            m_placeholders = ", ".join(["?"] * len(mileage_ext))
            self.conn.execute(
                f"INSERT INTO mileage_extents ({', '.join(m_cols)}) VALUES ({m_placeholders})", 
                m_vals
            )

    # ──────────────────────────────────────────────
    # spatial_extents 表操作
    # ──────────────────────────────────────────────
    def insert_spatial_extent(self, ext: SpatialExtent) -> None:
        self.conn.execute(
            """
            INSERT INTO spatial_extents (
                dataset_id, crs,
                bbox_minx, bbox_miny, bbox_maxx, bbox_maxy,
                bbox_minz, bbox_maxz, resolution_m, map_scale
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [ext.dataset_id, ext.crs,
             ext.bbox_minx, ext.bbox_miny, ext.bbox_maxx, ext.bbox_maxy,
             ext.bbox_minz, ext.bbox_maxz, ext.resolution_m, ext.map_scale],
        )

    def get_spatial_extent(self, dataset_id: str) -> Optional[dict[str, Any]]:
        return self._fetchone(
            "SELECT * FROM spatial_extents WHERE dataset_id = ?", [dataset_id]
        )

    # ──────────────────────────────────────────────
    # mileage_extents 表操作
    # ──────────────────────────────────────────────
    def insert_mileage_extent(self, ext: MileageExtent) -> None:
        self.conn.execute(
            """
            INSERT INTO mileage_extents (
                dataset_id,
                start_mileage, end_mileage,
                offset_lateral, offset_vertical,
                measurement_dir
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            [ext.dataset_id,
             ext.start_mileage, ext.end_mileage,
             ext.offset_lateral, ext.offset_vertical,
             ext.measurement_dir],
        )

    def get_mileage_extent(self, dataset_id: str) -> Optional[dict[str, Any]]:
        return self._fetchone(
            "SELECT * FROM mileage_extents WHERE dataset_id = ?", [dataset_id]
        )

    # ──────────────────────────────────────────────
    # processing_history 表操作
    # ──────────────────────────────────────────────
    def insert_processing_history(self, record: ProcessingHistory) -> int:
        result = self.conn.execute(
            """
            INSERT INTO processing_history (
                project_id, site_id,
                agent_name, tool_name,
                input_datasets, output_datasets,
                parameters, status, error_message, duration_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?) RETURNING id
            """,
            [
                record.project_id, record.site_id,
                record.agent_name, record.tool_name,
                json.dumps(record.input_datasets) if record.input_datasets else None,
                json.dumps(record.output_datasets) if record.output_datasets else None,
                json.dumps(record.parameters) if record.parameters else None,
                record.status, record.error_message, record.duration_ms,
            ],
        ).fetchone()
        return result[0]

    def update_processing_status(
        self,
        history_id: int,
        status: str,
        error_message: Optional[str] = None,
        duration_ms: Optional[int] = None,
        output_datasets: Optional[list[str]] = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE processing_history
            SET status=?, error_message=?, duration_ms=?, output_datasets=?
            WHERE id=?
            """,
            [
                status, error_message, duration_ms,
                json.dumps(output_datasets) if output_datasets else None,
                history_id,
            ],
        )

    # ──────────────────────────────────────────────
    # model_registry 表操作
    # ──────────────────────────────────────────────
    def insert_model(self, model: ModelRegistry) -> str:
        self.conn.execute(
            """
            INSERT INTO model_registry (
                id, project_id, site_id, name, description, positioning_type,
                voxel_resolution, grid_nx, grid_ny, grid_nz,
                crs_epsg,
                bbox_minx, bbox_miny, bbox_minz,
                bbox_maxx, bbox_maxy, bbox_maxz,
                centerline_id, start_mileage, end_mileage, model_radius,
                file_path, file_format, file_size_mb,
                attributes, input_dataset_ids, processing_ids, version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                model.id, model.project_id, model.site_id,
                model.name, model.description, model.positioning_type,
                model.voxel_resolution, model.grid_nx, model.grid_ny, model.grid_nz,
                model.crs_epsg,
                model.bbox_minx, model.bbox_miny, model.bbox_minz,
                model.bbox_maxx, model.bbox_maxy, model.bbox_maxz,
                model.centerline_id, model.start_mileage, model.end_mileage, model.model_radius,
                model.file_path, model.file_format, model.file_size_mb,
                json.dumps(model.attributes) if model.attributes else None,
                json.dumps(model.input_dataset_ids) if model.input_dataset_ids else None,
                json.dumps(model.processing_ids) if model.processing_ids else None,
                model.version,
            ],
        )
        return model.id

    def get_model(self, model_id: str) -> Optional[dict[str, Any]]:
        return self._fetchone("SELECT * FROM model_registry WHERE id = ?", [model_id])

    def list_models(
        self,
        project_id: Optional[str] = None,
        site_id: Optional[str] = None,
    ) -> list[dict[str, Any]]:
        conditions, params = [], []
        if project_id:
            conditions.append("project_id = ?")
            params.append(project_id)
        if site_id:
            conditions.append("site_id = ?")
            params.append(site_id)
        where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        return self._fetchall(
            f"SELECT * FROM model_registry {where} ORDER BY created_at DESC", params
        )


# 全局单例
db = DBManager()
