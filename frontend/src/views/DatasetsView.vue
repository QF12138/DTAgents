<template>
  <div>
    <div class="page-header">
      <h2 class="page-title">数据集管理</h2>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon>新增数据集
      </el-button>
    </div>

    <!-- 筛选栏 -->
    <el-card shadow="never" class="filter-card">
      <el-form inline :model="filters">
        <el-form-item label="名称">
          <el-input v-model="filters.name" placeholder="模糊搜索" clearable style="width:160px" />
        </el-form-item>
        <el-form-item label="工程">
          <el-select v-model="filters.project_id" placeholder="全部" clearable style="width:150px">
            <el-option v-for="p in projectOptions" :key="p.project_id" :label="p.name" :value="p.project_id" />
          </el-select>
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="filters.data_type" placeholder="全部" clearable style="width:120px">
            <el-option v-for="t in DATA_TYPES" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="定位类型">
          <el-select v-model="filters.positioning_type" placeholder="全部" clearable style="width:120px">
            <el-option label="空间坐标" value="spatial" />
            <el-option label="里程定位" value="mileage" />
            <el-option label="双重定位" value="both" />
          </el-select>
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" placeholder="全部" clearable style="width:120px">
            <el-option v-for="s in STATUSES" :key="s.value" :label="s.label" :value="s.value" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchData">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 数据表 -->
    <el-card shadow="never" class="table-card">
      <el-table :data="rows" v-loading="loading" stripe border style="width:100%">
        <el-table-column prop="name"             label="名称"     min-width="140" show-overflow-tooltip />
        <el-table-column prop="project_id"       label="工程"     min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ projectName(row.project_id) }}</template>
        </el-table-column>
        <el-table-column prop="description"      label="介绍"     min-width="180" show-overflow-tooltip />
        <el-table-column prop="data_type"        label="类型"     width="80">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ row.data_type }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="positioning_type" label="定位"     width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="posType(row.positioning_type)">{{ posLabel(row.positioning_type) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="file_format"      label="格式"     width="90" />
        <el-table-column prop="status"           label="状态"     width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="quality_flag"     label="质量"     width="70" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="qualityType(row.quality_flag)">{{ QUALITY[row.quality_flag] }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="file_size_mb"     label="大小(MB)" width="90" align="right">
          <template #default="{ row }">{{ row.file_size_mb?.toFixed(2) ?? '—' }}</template>
        </el-table-column>
        <el-table-column prop="created_at"       label="创建时间" width="160" />
        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
            <el-popconfirm title="确认删除？" @confirm="doDelete(row.id)">
              <template #reference>
                <el-button link type="danger">删除</el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="size"
          :total="total"
          :page-sizes="[10, 20, 50]"
          layout="total, sizes, prev, pager, next"
          @change="fetchData"
        />
      </div>
    </el-card>

    <!-- 新增/编辑弹窗 -->
    <el-dialog v-model="dialogVisible" :title="editId ? '编辑数据集' : '新增数据集'"
      width="760px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px" label-position="right">

        <el-divider content-position="left">基本信息</el-divider>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="名称" prop="name">
              <el-input v-model="form.name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="数据类型" prop="data_type">
              <el-select v-model="form.data_type" style="width:100%">
                <el-option v-for="t in DATA_TYPES" :key="t" :label="t" :value="t" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="所属工程">
              <el-select v-model="form.project_id" placeholder="请选择" clearable style="width:100%"
                @change="onProjectChange">
                <el-option v-for="p in projectOptions" :key="p.project_id" :label="p.name" :value="p.project_id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="所属工点">
              <el-select v-model="form.site_id" placeholder="请先选工程" clearable style="width:100%"
                :disabled="!form.project_id">
                <el-option v-for="s in siteOptions" :key="s.site_id" :label="s.name" :value="s.site_id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="文件路径" prop="file_path">
          <el-input v-model="form.file_path" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="文件格式">
              <el-input v-model="form.file_format" placeholder="GeoTIFF / SHP / CSV…" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="文件大小(MB)">
              <el-input-number v-model="form.file_size_mb" :precision="2" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="起始日期">
              <el-input v-model="form.survey_date_start" placeholder="YYYY-MM-DD" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="结束日期">
              <el-input v-model="form.survey_date_end" placeholder="YYYY-MM-DD" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>

        <el-divider content-position="left">定位类型</el-divider>
        <el-form-item label="定位方式" prop="positioning_type">
          <el-radio-group v-model="form.positioning_type">
            <el-radio-button :value="'spatial'">空间坐标</el-radio-button>
            <el-radio-button :value="'mileage'">里程定位</el-radio-button>
            <el-radio-button :value="'both'">双重定位</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <!-- 空间范围 -->
        <template v-if="form.positioning_type === 'spatial' || form.positioning_type === 'both'">
          <el-divider content-position="left">空间范围</el-divider>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="坐标系(CRS)">
                <el-input v-model="form.spatial.crs" placeholder="EPSG:4547" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="分辨率(m)">
                <el-input-number v-model="form.spatial.resolution_m" :precision="4" :controls="false" style="width:100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="地图比例尺">
                <el-input v-model="form.spatial.map_scale" placeholder="1:500" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8" v-for="f in spatialBboxFields" :key="f.key">
              <el-form-item :label="f.label">
                <el-input-number v-model="form.spatial[f.key]" :precision="4" :controls="false" style="width:100%" />
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <!-- 里程范围 -->
        <template v-if="form.positioning_type === 'mileage' || form.positioning_type === 'both'">
          <el-divider content-position="left">里程范围</el-divider>
          <el-row :gutter="16">
            <el-col :span="12">
              <el-form-item label="起始里程(m)">
                <el-input-number v-model="form.mileage.start_mileage" :controls="false" style="width:100%" />
              </el-form-item>
            </el-col>
            <el-col :span="12">
              <el-form-item label="终止里程(m)">
                <el-input-number v-model="form.mileage.end_mileage" :controls="false" style="width:100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="横向偏移(m)">
                <el-input-number v-model="form.mileage.offset_lateral" :precision="3" :controls="false" style="width:100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="竖向偏移(m)">
                <el-input-number v-model="form.mileage.offset_vertical" :precision="3" :controls="false" style="width:100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="量测方向">
                <el-input v-model="form.mileage.measurement_dir" placeholder="forward / backward" />
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <el-divider content-position="left">质量与状态</el-divider>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="状态">
              <el-select v-model="form.status" style="width:100%">
                <el-option v-for="s in STATUSES" :key="s.value" :label="s.label" :value="s.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="质量标志">
              <el-select v-model="form.quality_flag" style="width:100%">
                <el-option v-for="(label, val) in QUALITY" :key="val" :label="`${val} - ${label}`" :value="Number(val)" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="标签">
          <el-select v-model="form.tags" multiple allow-create filterable style="width:100%"
            placeholder="输入后回车添加" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="doSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  listDatasets, getDataset, createDataset, updateDataset, deleteDataset,
  listProjects, listWorkSites,
} from '../api/index.js'

const DATA_TYPES = ['DEM','DOM','DRL','EGM','ECL','PRF','BIM',
                    'TSP','TEM','GPR','AHD','DBH','TFR','TBM','RDR','IST','EMS']
const STATUSES   = [
  { value: 'raw',       label: 'raw（原始）'       },
  { value: 'validated', label: 'validated（已验证）' },
  { value: 'processed', label: 'processed（已处理）' },
  { value: 'archived',  label: 'archived（已归档）'  },
]
const QUALITY = { 0: '未验证', 1: '通过', 2: '警告', 3: '失败' }

const spatialBboxFields = [
  { key: 'bbox_minx', label: 'MinX' }, { key: 'bbox_maxx', label: 'MaxX' },
  { key: 'bbox_miny', label: 'MinY' }, { key: 'bbox_maxy', label: 'MaxY' },
  { key: 'bbox_minz', label: 'MinZ' }, { key: 'bbox_maxz', label: 'MaxZ' },
]

const projectName = (pid) => projectOptions.value.find(p => p.project_id === pid)?.name ?? '—'

const posType  = t => ({ spatial: 'primary', mileage: 'success', both: '' }[t] ?? 'info')
const posLabel = t => ({ spatial: '空间', mileage: '里程', both: '双重' }[t] ?? t)
const statusType  = s => ({ raw:'info', validated:'primary', processed:'success', archived:'warning' }[s] ?? '')
const qualityType = q => (['info','success','warning','danger'][q] ?? 'info')

// ── state ─────────────────────────────────────────────────────────────────────
const loading  = ref(false)
const saving   = ref(false)
const forming  = ref(false)
const rows     = ref([])
const total    = ref(0)
const page     = ref(1)
const size     = ref(20)
const filters  = reactive({ name: '', project_id: '', data_type: '', status: '', positioning_type: '' })

const projectOptions    = ref([])
const siteOptions       = ref([])

// ── form ──────────────────────────────────────────────────────────────────────
const dialogVisible = ref(false)
const editId  = ref(null)
const formRef = ref()
const rules   = {
  name:             [{ required: true, message: '请输入名称' }],
  data_type:        [{ required: true, message: '请选择数据类型' }],
  file_path:        [{ required: true, message: '请输入文件路径' }],
  positioning_type: [{ required: true, message: '请选择定位类型' }],
}

const emptyForm = () => ({
  project_id: '', site_id: '', name: '', data_type: '',
  positioning_type: 'spatial',
  file_path: '', file_format: '', file_size_mb: null, checksum: '',
  survey_date_start: '', survey_date_end: '',
  status: 'raw', quality_flag: 0, tags: [], description: '',
  spatial: { crs: 'EPSG:4547', bbox_minx: null, bbox_miny: null, bbox_minz: null,
             bbox_maxx: null, bbox_maxy: null, bbox_maxz: null,
             resolution_m: null, map_scale: '' },
  mileage: { start_mileage: null, end_mileage: null,
             offset_lateral: 0, offset_vertical: 0, measurement_dir: '' },
})
const form = reactive(emptyForm())

// ── watch project change → load site options ──────────────────────────────────
watch(() => form.project_id, async (pid) => {
  siteOptions.value = []
  if (!pid) return
  const wsRes = await listWorkSites({ project_id: pid, size: 50 })
  siteOptions.value = wsRes.items
})

function onProjectChange() {}  // watch handles it

// ── methods ───────────────────────────────────────────────────────────────────
async function fetchData() {
  loading.value = true
  try {
    const params = { page: page.value, size: size.value }
    if (filters.name)             params.name             = filters.name
    if (filters.project_id)       params.project_id       = filters.project_id
    if (filters.data_type)        params.data_type        = filters.data_type
    if (filters.status)           params.status           = filters.status
    if (filters.positioning_type) params.positioning_type = filters.positioning_type
    const res = await listDatasets(params)
    rows.value  = res.items
    total.value = res.total
  } finally { loading.value = false }
}

async function loadProjectOptions() {
  const res = await listProjects({ size: 50 })
  projectOptions.value = res.items
}

function resetFilters() {
  Object.assign(filters, { name: '', project_id: '', data_type: '', status: '', positioning_type: '' })
  page.value = 1
  fetchData()
}

function openCreate() {
  editId.value = null
  Object.assign(form, emptyForm())
  dialogVisible.value = true
}

async function openEdit(row) {
  editId.value = row.id
  // Fetch full detail with JOIN data
  const d = await getDataset(row.id)
  const f = emptyForm()
  // Map basic fields
  Object.assign(f, {
    project_id: d.project_id || '', site_id: d.site_id || '',
    name: d.name, data_type: d.data_type, positioning_type: d.positioning_type || 'spatial',
    file_path: d.file_path, file_format: d.file_format || '',
    file_size_mb: d.file_size_mb, checksum: d.checksum || '',
    survey_date_start: d.survey_date_start || '', survey_date_end: d.survey_date_end || '',
    status: d.status, quality_flag: d.quality_flag,
    tags: d.tags ? (typeof d.tags === 'string' ? JSON.parse(d.tags) : d.tags) : [],
    description: d.description || '',
  })
  // Map spatial extents (s_* prefix from JOIN)
  if (d.s_crs !== null && d.s_crs !== undefined) {
    f.spatial = {
      crs: d.s_crs || 'EPSG:4547',
      bbox_minx: d.s_bbox_minx, bbox_miny: d.s_bbox_miny, bbox_minz: d.s_bbox_minz,
      bbox_maxx: d.s_bbox_maxx, bbox_maxy: d.s_bbox_maxy, bbox_maxz: d.s_bbox_maxz,
      resolution_m: d.s_resolution_m, map_scale: d.s_map_scale || '',
    }
  }
  // Map mileage extents (m_* prefix from JOIN)
  if (d.m_start_mileage !== null && d.m_start_mileage !== undefined) {
    f.mileage = {
      start_mileage: d.m_start_mileage, end_mileage: d.m_end_mileage,
      offset_lateral: d.m_offset_lateral ?? 0, offset_vertical: d.m_offset_vertical ?? 0,
      measurement_dir: d.m_measurement_dir || '',
    }
  }
  Object.assign(form, f)
  dialogVisible.value = true
}

async function doSave() {
  await formRef.value.validate()
  saving.value = true
  try {
    const pt = form.positioning_type
    const body = {
      project_id: form.project_id || null,
      site_id:    form.site_id    || null,
      name: form.name, data_type: form.data_type,
      positioning_type: pt,
      file_path: form.file_path, file_format: form.file_format || null,
      file_size_mb: form.file_size_mb, checksum: form.checksum || null,
      survey_date_start: form.survey_date_start || null,
      survey_date_end:   form.survey_date_end   || null,
      status: form.status, quality_flag: form.quality_flag,
      tags: form.tags.length ? form.tags : null,
      description: form.description || null,
      spatial: (pt === 'spatial' || pt === 'both') ? { ...form.spatial } : null,
      mileage: (pt === 'mileage' || pt === 'both') ? { ...form.mileage } : null,
    }
    if (editId.value) {
      await updateDataset(editId.value, body)
      ElMessage.success('更新成功')
    } else {
      await createDataset(body)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    fetchData()
  } finally { saving.value = false }
}

async function doDelete(id) {
  await deleteDataset(id)
  ElMessage.success('已删除')
  fetchData()
}

onMounted(
async () => {
  try {
    await fetchData()
    await loadProjectOptions()
  } catch (error) {
    console.error('初始化数据失败:', error)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.page-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }
.page-title  { font-size:20px; font-weight:600; color:#1a2332; }
.filter-card, .table-card { border-radius:8px; margin-bottom:16px; }
.filter-card :deep(.el-card__body) { padding:16px 20px 4px; }
.pagination  { margin-top:16px; display:flex; justify-content:flex-end; }
</style>
