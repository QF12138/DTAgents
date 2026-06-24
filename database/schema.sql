-- ============================================================
-- 三维空间建模系统 - 元数据索引数据库 Schema v3
-- 数据库引擎: DuckDB
--
-- 设计原则：
--   DTAgents 只存储元数据（MetaData），不存储实际数据内容。
--   几何数据、点云、栅格等均通过 file_path 引用外部文件。
--
-- 层级关系（简化后）：
--   projects → work_sites
--   work_sites.centerline_id → datasets.id   （中线本身就是线路数据集）
--   work_sites.profile_id    → datasets.id   （设计断面轮廓数据集）
--
-- 表结构（共 7 张）：
--   工程层级：projects → work_sites
--   数据管理：datasets → spatial_extents / mileage_extents
--   过程记录：processing_history
--   成果注册：model_registry
-- ============================================================


-- ============================================================
-- 1. 工程项目表（顶层）
-- ============================================================
CREATE TABLE IF NOT EXISTS projects (
    project_id  VARCHAR PRIMARY KEY,            -- UUID
    name        VARCHAR NOT NULL,               -- 如"某铁路TJ01标"
    type        VARCHAR,                        -- highway|railway|metro|municipal|waterway
    description TEXT,
    default_crs VARCHAR DEFAULT 'EPSG:4547',    -- 工程默认坐标系
    created_at  TIMESTAMP DEFAULT current_timestamp
);


-- ============================================================
-- 2. 工点表（工程 → 工点，1:N）
--
--    工点是工程中具有专属名称的施工区段，如：
--      "旗山隧道进口段" DK12+340 ~ DK14+200
--      "旗山隧道出口段" DK14+200 ~ DK16+580
--
--    centerline_id / profile_id 逻辑上引用 datasets.id，
--    但为避免与 datasets.site_id → work_sites 形成循环外键，
--    此处不声明 FK 约束，由应用层（hierarchy.py / server.py）负责校验。
-- ============================================================
CREATE TABLE IF NOT EXISTS work_sites (
    site_id                VARCHAR PRIMARY KEY,         -- UUID
    project_id             VARCHAR NOT NULL REFERENCES projects(project_id),
    name                   VARCHAR NOT NULL,            -- 工点名称
    type                   VARCHAR,                     -- 正洞|平导|斜井|横洞|明洞
    mileage_prefix         VARCHAR,                     -- 里程冠号，如 X1DK、ZDK、YDK，唯一标识线路/中线
    centerline_id          VARCHAR,                     -- 逻辑引用 datasets.id，应用层校验
    profile_id             VARCHAR,                     -- 逻辑引用 datasets.id，应用层校验
    construction_direction VARCHAR,                     -- 施工推进方向：forward（大里程）| backward（小里程）
    start_mileage          DOUBLE,                      -- 工点起始里程（m），可为 NULL
    end_mileage            DOUBLE,                      -- 工点终止里程（m），可为 NULL
    description            TEXT,
    created_at             TIMESTAMP DEFAULT current_timestamp
);
-- 兼容旧库：若 mileage_prefix 列不存在则补充添加
ALTER TABLE work_sites ADD COLUMN IF NOT EXISTS mileage_prefix VARCHAR;


-- ============================================================
-- 3. 数据集基础表
--
--    仅含业务身份和管理字段，不含任何坐标或里程字段。
--    定位信息全部移至 spatial_extents / mileage_extents。
--    类型特定属性通过 extra_meta（JSON）存储。
--
--    data_type 说明：
--      工程/区域类：DEM DOM DRL EGM BIM
--      洞内/里程类：TSP TEM GPR AHD DBH
--                  TFR TBM RDR IST EMS
-- ============================================================
CREATE TABLE IF NOT EXISTS datasets (
    id               VARCHAR PRIMARY KEY,       -- UUID
    project_id       VARCHAR REFERENCES projects(project_id),
    site_id          VARCHAR REFERENCES work_sites(site_id),  -- 可为 NULL（跨工点数据）
    name             VARCHAR NOT NULL,
    data_type        VARCHAR NOT NULL,          -- 见上方说明
    positioning_type VARCHAR NOT NULL,          -- spatial | mileage | both
    file_path        VARCHAR NOT NULL,          -- 数据文件路径（元数据引用）
    file_format      VARCHAR,                   -- GeoTIFF|SHP|CSV|LAS|SEG-Y|HDF5|IFC ...
    file_size_mb     DOUBLE,
    checksum         VARCHAR,                   -- MD5，用于变更检测
    survey_date_start VARCHAR,                  -- 采集开始日期（ISO8601）
    survey_date_end   VARCHAR,                  -- 采集结束日期（ISO8601）
    status           VARCHAR DEFAULT 'raw',     -- raw|validated|processed|archived
    quality_flag     INTEGER DEFAULT 0,         -- 0:未验证 1:通过 2:警告 3:失败
    tags             VARCHAR,                   -- JSON 数组，如 ["2024","进口段"]
    description      VARCHAR,
    extra_meta       VARCHAR,                   -- JSON，类型特定属性
    created_at       TIMESTAMP DEFAULT current_timestamp,
    updated_at       TIMESTAMP DEFAULT current_timestamp
);


-- ============================================================
-- 4. 地理空间范围表（大地坐标 / 投影坐标定位）
--
--    适用：DEM DOM EGM BIM 等地表测量数据
--    与 datasets 为 1:1 关系，
--    仅 positioning_type IN ('spatial', 'both') 时存在对应记录。
-- ============================================================
CREATE TABLE IF NOT EXISTS spatial_extents (
    dataset_id   VARCHAR PRIMARY KEY REFERENCES datasets(id),
    crs          VARCHAR NOT NULL,              -- 如 'EPSG:4547'
    bbox_minx    DOUBLE,                        -- 最小 X（东向，单位与 CRS 一致）
    bbox_miny    DOUBLE,                        -- 最小 Y（北向）
    bbox_maxx    DOUBLE,
    bbox_maxy    DOUBLE,
    bbox_minz    DOUBLE,                        -- 最小高程（m），二维数据为 NULL
    bbox_maxz    DOUBLE,
    resolution_m DOUBLE,                        -- 空间分辨率（m），栅格数据填写
    map_scale    VARCHAR                        -- 比例尺，如 '1:2000'
);


-- ============================================================
-- 5. 里程范围表（里程定位）
--
--    适用：TSP GPR TEM 等洞内数据
--    与 datasets 为 1:1 关系，
--    仅 positioning_type IN ('mileage', 'both') 时存在对应记录。
--
--    中线关联通过 datasets.site_id → work_sites.centerline_id 间接获取，
--    不在本表冗余存储。
-- ============================================================
CREATE TABLE IF NOT EXISTS mileage_extents (
    dataset_id      VARCHAR PRIMARY KEY REFERENCES datasets(id),
    start_mileage   DOUBLE NOT NULL,            -- 起始里程（m）
    end_mileage     DOUBLE,                     -- 终止里程（m），NULL 表示点状数据

    -- 相对中线的横断面偏移（适用于偏中线布置的测线/传感器）
    offset_lateral  DOUBLE DEFAULT 0,           -- 横向偏移（m，右正左负）
    offset_vertical DOUBLE DEFAULT 0,           -- 竖向偏移（m，上正下负）

    measurement_dir VARCHAR                     -- forward | backward（相对推进方向）
);


-- ============================================================
-- 6. 处理历史表（操作日志，支持溯源）
-- ============================================================
CREATE SEQUENCE IF NOT EXISTS seq_processing_history_id START 1;
CREATE TABLE IF NOT EXISTS processing_history (
    id              BIGINT DEFAULT nextval('seq_processing_history_id') PRIMARY KEY,
    project_id      VARCHAR REFERENCES projects(project_id),
    site_id         VARCHAR REFERENCES work_sites(site_id),
    agent_name      VARCHAR NOT NULL,           -- InitializationAgent 等
    tool_name       VARCHAR NOT NULL,           -- interpolate_spatial 等
    input_datasets  VARCHAR,                    -- JSON 数组 [dataset_id, ...]
    output_datasets VARCHAR,                    -- JSON 数组 [dataset_id, ...]
    parameters      VARCHAR,                    -- JSON，工具调用参数快照
    status          VARCHAR DEFAULT 'pending',  -- pending|running|success|failed
    error_message   VARCHAR,
    duration_ms     INTEGER,
    created_at      TIMESTAMP DEFAULT current_timestamp
);


-- ============================================================
-- 7. 地质模型注册表（支持地理坐标和里程双坐标体系）
--
--    centerline_id → datasets.id（中线数据集）
-- ============================================================
CREATE TABLE IF NOT EXISTS model_registry (
    id               VARCHAR PRIMARY KEY,       -- UUID
    project_id       VARCHAR REFERENCES projects(project_id),
    site_id          VARCHAR REFERENCES work_sites(site_id),
    name             VARCHAR NOT NULL,
    description      VARCHAR,
    positioning_type VARCHAR NOT NULL DEFAULT 'spatial',  -- spatial | mileage

    -- 体素网格参数
    voxel_resolution DOUBLE,                    -- 网格分辨率（m）
    grid_nx          INTEGER,
    grid_ny          INTEGER,
    grid_nz          INTEGER,

    -- 地理坐标范围（positioning_type = 'spatial' 时填写）
    crs_epsg         INTEGER,
    bbox_minx DOUBLE, bbox_miny DOUBLE, bbox_minz DOUBLE,
    bbox_maxx DOUBLE, bbox_maxy DOUBLE, bbox_maxz DOUBLE,

    -- 里程范围（positioning_type = 'mileage' 时填写）
    centerline_id    VARCHAR REFERENCES datasets(id),   -- 关联中线数据集
    start_mileage   DOUBLE,                    -- 模型起始里程（m）
    end_mileage     DOUBLE,                    -- 模型终止里程（m）
    model_radius     DOUBLE,                    -- 建模半径（m，以中线为轴）

    -- 文件存储（元数据引用）
    file_path        VARCHAR,                   -- VTK/NPZ/HDF5 文件路径
    file_format      VARCHAR,
    file_size_mb     DOUBLE,

    -- 来源追踪
    attributes       VARCHAR,                   -- JSON 数组，模型包含的属性列表
    input_dataset_ids VARCHAR,                  -- JSON 数组
    processing_ids   VARCHAR,                   -- JSON 数组，关联 processing_history

    created_at       TIMESTAMP DEFAULT current_timestamp,
    version          INTEGER DEFAULT 1
);


-- ============================================================
-- 索引
-- ============================================================

-- 工点
CREATE INDEX IF NOT EXISTS idx_work_sites_project        ON work_sites(project_id);
CREATE INDEX IF NOT EXISTS idx_work_sites_centerline     ON work_sites(centerline_id);
CREATE INDEX IF NOT EXISTS idx_work_sites_mileage        ON work_sites(start_mileage, end_mileage);
CREATE INDEX IF NOT EXISTS idx_work_sites_mileage_prefix ON work_sites(mileage_prefix);

-- 数据集
CREATE INDEX IF NOT EXISTS idx_datasets_project       ON datasets(project_id);
CREATE INDEX IF NOT EXISTS idx_datasets_site          ON datasets(site_id);
CREATE INDEX IF NOT EXISTS idx_datasets_type          ON datasets(data_type);
CREATE INDEX IF NOT EXISTS idx_datasets_pos_type      ON datasets(positioning_type);
CREATE INDEX IF NOT EXISTS idx_datasets_status        ON datasets(status);

-- 里程范围
CREATE INDEX IF NOT EXISTS idx_mileage_start          ON mileage_extents(start_mileage);
CREATE INDEX IF NOT EXISTS idx_mileage_end            ON mileage_extents(end_mileage);

-- 处理历史
CREATE INDEX IF NOT EXISTS idx_proc_history_project   ON processing_history(project_id);
CREATE INDEX IF NOT EXISTS idx_proc_history_agent     ON processing_history(agent_name);
CREATE INDEX IF NOT EXISTS idx_proc_history_status    ON processing_history(status);
