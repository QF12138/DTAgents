<template>
  <div>
    <div class="page-header">
      <h2 class="page-title">地质模型管理</h2>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon>新增模型
      </el-button>
    </div>

    <el-card shadow="never" class="filter-card">
      <el-form inline :model="filters">
        <el-form-item label="名称">
          <el-input v-model="filters.name" placeholder="模糊搜索" clearable style="width:180px" />
        </el-form-item>
        <el-form-item label="工程">
          <el-select v-model="filters.project_id" placeholder="全部" clearable style="width:150px">
            <el-option v-for="p in projectOptions" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="定位类型">
          <el-select v-model="filters.positioning_type" placeholder="全部" clearable style="width:120px">
            <el-option label="空间坐标" value="spatial" />
            <el-option label="里程定位" value="mileage" />
          </el-select>
        </el-form-item>
        <el-form-item>
          <el-button type="primary" @click="fetchData">查询</el-button>
          <el-button @click="resetFilters">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="table-card">
      <el-table :data="rows" v-loading="loading" stripe border style="width:100%">
        <el-table-column prop="name"             label="名称"       min-width="160" show-overflow-tooltip />
        <el-table-column prop="positioning_type" label="定位"       width="90">
          <template #default="{ row }">
            <el-tag size="small" :type="row.positioning_type === 'spatial' ? 'primary' : 'success'">
              {{ row.positioning_type === 'spatial' ? '空间' : '里程' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="voxel_resolution" label="体素分辨率"  width="100" align="right">
          <template #default="{ row }">{{ row.voxel_resolution ?? '—' }}</template>
        </el-table-column>
        <el-table-column label="网格(NxNyNz)" width="130" align="center">
          <template #default="{ row }">
            <span v-if="row.grid_nx">{{ row.grid_nx }}×{{ row.grid_ny }}×{{ row.grid_nz }}</span>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column prop="file_format"  label="格式"     width="90" />
        <el-table-column prop="file_size_mb" label="大小(MB)" width="90" align="right">
          <template #default="{ row }">{{ row.file_size_mb?.toFixed(2) ?? '—' }}</template>
        </el-table-column>
        <el-table-column prop="version"      label="版本"     width="65"  align="center" />
        <el-table-column prop="created_at"   label="创建时间" width="160" />
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

    <el-dialog v-model="dialogVisible" :title="editId ? '编辑地质模型' : '新增地质模型'"
      width="700px" destroy-on-close>
      <el-form ref="formRef" :model="form" :rules="rules" label-width="110px">

        <el-divider content-position="left">基本信息</el-divider>
        <el-form-item label="名称" prop="name">
          <el-input v-model="form.name" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="所属工程">
              <el-select v-model="form.project_id" placeholder="请选择" clearable style="width:100%"
                @change="onProjectChange">
                <el-option v-for="p in projectOptions" :key="p.id" :label="p.name" :value="p.id" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="所属工点">
              <el-select v-model="form.site_id" placeholder="请先选工程" clearable style="width:100%"
                :disabled="!form.project_id">
                <el-option v-for="s in siteOptions" :key="s.id" :label="s.name" :value="s.id" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" />
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="8">
            <el-form-item label="文件格式">
              <el-input v-model="form.file_format" placeholder="VTK/NPZ/HDF5" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="文件大小(MB)">
              <el-input-number v-model="form.file_size_mb" :precision="2" :controls="false" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="版本">
              <el-input-number v-model="form.version" :min="1" :controls="false" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="文件路径">
          <el-input v-model="form.file_path" />
        </el-form-item>

        <el-divider content-position="left">定位类型</el-divider>
        <el-form-item label="定位方式">
          <el-radio-group v-model="form.positioning_type">
            <el-radio-button :value="'spatial'">空间坐标</el-radio-button>
            <el-radio-button :value="'mileage'">里程定位</el-radio-button>
          </el-radio-group>
        </el-form-item>

        <!-- 空间坐标 -->
        <template v-if="form.positioning_type === 'spatial'">
          <el-divider content-position="left">空间范围</el-divider>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="EPSG">
                <el-input-number v-model="form.crs_epsg" :controls="false" style="width:100%" />
              </el-form-item>
            </el-col>
          </el-row>
          <el-row :gutter="16">
            <el-col :span="8" v-for="f in bboxFields" :key="f.key">
              <el-form-item :label="f.label">
                <el-input-number v-model="form[f.key]" :precision="4" :controls="false" style="width:100%" />
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <!-- 里程定位 -->
        <template v-if="form.positioning_type === 'mileage'">
          <el-divider content-position="left">里程范围</el-divider>
          <el-form-item label="关联中线">
            <el-select v-model="form.centerline_id" placeholder="请先选工程" clearable style="width:100%"
              :disabled="!form.project_id">
              <el-option v-for="cl in centerlineOptions" :key="cl.id" :label="cl.name" :value="cl.id" />
            </el-select>
          </el-form-item>
          <el-row :gutter="16">
            <el-col :span="8">
              <el-form-item label="起始里程(m)">
                <el-input-number v-model="form.start_mileage" :controls="false" style="width:100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="终止里程(m)">
                <el-input-number v-model="form.end_mileage" :controls="false" style="width:100%" />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="模型半径(m)">
                <el-input-number v-model="form.model_radius" :precision="2" :controls="false" style="width:100%" />
              </el-form-item>
            </el-col>
          </el-row>
        </template>

        <el-divider content-position="left">网格参数</el-divider>
        <el-row :gutter="16">
          <el-col :span="6">
            <el-form-item label="分辨率(m)">
              <el-input-number v-model="form.voxel_resolution" :precision="2" :controls="false" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="Nx">
              <el-input-number v-model="form.grid_nx" :controls="false" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="Ny">
              <el-input-number v-model="form.grid_ny" :controls="false" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="6">
            <el-form-item label="Nz">
              <el-input-number v-model="form.grid_nz" :controls="false" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
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
import { listModels, createModel, updateModel, deleteModel,
         listProjects, listWorkSites } from '../api/index.js'

const bboxFields = [
  { key: 'bbox_minx', label: 'MinX' }, { key: 'bbox_maxx', label: 'MaxX' },
  { key: 'bbox_miny', label: 'MinY' }, { key: 'bbox_maxy', label: 'MaxY' },
  { key: 'bbox_minz', label: 'MinZ' }, { key: 'bbox_maxz', label: 'MaxZ' },
]

const loading = ref(false)
const saving  = ref(false)
const rows    = ref([])
const total   = ref(0)
const page    = ref(1)
const size    = ref(20)
const filters = reactive({ name: '', project_id: '', positioning_type: '' })

const projectOptions    = ref([])
const siteOptions       = ref([])
const centerlineOptions = ref([])

const dialogVisible = ref(false)
const editId  = ref(null)
const formRef = ref()
const rules   = { name: [{ required: true, message: '请输入名称' }] }

const emptyForm = () => ({
  name: '', description: '',
  project_id: '', site_id: '',
  positioning_type: 'spatial',
  crs_epsg: null,
  bbox_minx: null, bbox_miny: null, bbox_minz: null,
  bbox_maxx: null, bbox_maxy: null, bbox_maxz: null,
  centerline_id: '', start_mileage: null, end_mileage: null, model_radius: null,
  voxel_resolution: null, grid_nx: null, grid_ny: null, grid_nz: null,
  file_path: '', file_format: '', file_size_mb: null, version: 1,
  attributes: null, input_dataset_ids: null, processing_ids: null,
})
const form = reactive(emptyForm())

watch(() => form.project_id, async (pid) => {
  siteOptions.value       = []
  centerlineOptions.value = []
  form.site_id            = ''
  form.centerline_id      = ''
  if (!pid) return
  const [wsRes, clRes] = await Promise.all([
    listWorkSites({ project_id: pid, size: 50 }),
    listCenterlines({ project_id: pid, size: 100 }),
  ])
  siteOptions.value       = wsRes.items
  centerlineOptions.value = clRes.items
})

function onProjectChange() {}

async function fetchData() {
  loading.value = true
  try {
    const params = { page: page.value, size: size.value }
    if (filters.name)             params.name             = filters.name
    if (filters.project_id)       params.project_id       = filters.project_id
    if (filters.positioning_type) params.positioning_type = filters.positioning_type
    const res = await listModels(params)
    rows.value  = res.items
    total.value = res.total
  } finally { loading.value = false }
}

async function loadProjectOptions() {
  const res = await listProjects({ size: 50 })
  projectOptions.value = res.items
}

function resetFilters() {
  Object.assign(filters, { name: '', project_id: '', positioning_type: '' })
  page.value = 1
  fetchData()
}

function openCreate() {
  editId.value = null
  Object.assign(form, emptyForm())
  dialogVisible.value = true
}

function openEdit(row) {
  editId.value = row.id
  Object.assign(form, emptyForm(), row, {
    project_id:    row.project_id    ?? '',
    site_id:       row.site_id       ?? '',
    centerline_id: row.centerline_id ?? '',
    positioning_type: row.positioning_type ?? 'spatial',
  })
  dialogVisible.value = true
}

async function doSave() {
  await formRef.value.validate()
  saving.value = true
  try {
    const body = { ...form }
    if (editId.value) {
      await updateModel(editId.value, body)
      ElMessage.success('更新成功')
    } else {
      await createModel(body)
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
    fetchData()
  } finally { saving.value = false }
}

async function doDelete(id) {
  await deleteModel(id)
  ElMessage.success('已删除')
  fetchData()
}

onMounted(() => {
  fetchData()
  loadProjectOptions()
})
</script>

<style scoped>
.page-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }
.page-title  { font-size:20px; font-weight:600; color:#1a2332; }
.filter-card, .table-card { border-radius:8px; margin-bottom:16px; }
.filter-card :deep(.el-card__body) { padding:16px 20px 4px; }
.pagination  { margin-top:16px; display:flex; justify-content:flex-end; }
</style>
