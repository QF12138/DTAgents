<template>
  <div>
    <div class="page-header">
      <h2 class="page-title">工程层级管理</h2>
      <el-button type="primary" @click="openProjectDialog()">
        <el-icon><Plus /></el-icon>新增工程
      </el-button>
    </div>

    <!-- 工程列表（折叠面板） -->
    <el-collapse v-model="openPanels" v-loading="loadingProjects" @change="onCollapseChange">
      <el-collapse-item
        v-for="proj in projects"
        :key="proj.project_id"
        :name="proj.project_id"
      >
        <template #title>
          <div class="collapse-title">
            <el-tag type="info" size="small" class="type-tag">{{ proj.type || '未分类' }}</el-tag>
            <span class="proj-name">{{ proj.name }}</span>
            <span class="proj-meta" v-if="proj.default_crs">{{ proj.default_crs }}</span>
            <div class="collapse-actions" @click.stop>
              <el-button link type="primary" size="small" @click="openProjectDialog(proj)">编辑</el-button>
              <el-popconfirm title="确认删除该工程？" @confirm="doDeleteProject(proj.project_id)">
                <template #reference>
                  <el-button link type="danger" size="small">删除</el-button>
                </template>
              </el-popconfirm>
              <el-button link type="success" size="small" @click.stop="openWorkSiteDialog(null, proj.project_id)">
                <el-icon><Plus /></el-icon>添加工点
              </el-button>
            </div>
          </div>
        </template>

        <!-- 工点表格 -->
        <el-table
          :data="workSitesByProject[proj.project_id] || []"
          v-loading="loadingWorkSites[proj.project_id]"
          stripe border style="width:100%"
          size="small"
        >
          <el-table-column prop="name" label="工点名称" min-width="150" show-overflow-tooltip />
          <el-table-column prop="type" label="类型" width="90" />
          <el-table-column label="里程冠号" width="90" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.mileage_prefix" type="success" size="small">{{ row.mileage_prefix }}</el-tag>
              <span v-else class="text-muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="施工方向" width="100" align="center">
            <template #default="{ row }">
              <el-tag v-if="row.construction_direction === 'forward'" type="primary" size="small">大里程</el-tag>
              <el-tag v-else-if="row.construction_direction === 'backward'" type="warning" size="small">小里程</el-tag>
              <span v-else class="text-muted">—</span>
            </template>
          </el-table-column>
          <el-table-column prop="start_mileage" label="起始里程(m)" width="115" align="right">
            <template #default="{ row }">{{ row.start_mileage ?? '—' }}</template>
          </el-table-column>
          <el-table-column prop="end_mileage" label="终止里程(m)" width="115" align="right">
            <template #default="{ row }">{{ row.end_mileage ?? '—' }}</template>
          </el-table-column>
          <el-table-column label="中线数据" min-width="130" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.centerline_id">{{ datasetName(row.centerline_id, proj.project_id) }}</span>
              <span v-else class="text-muted">—</span>
            </template>
          </el-table-column>
          <el-table-column label="断面轮廓" min-width="130" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="row.profile_id">{{ datasetName(row.profile_id, proj.project_id) }}</span>
              <span v-else class="text-muted">—</span>
            </template>
          </el-table-column>
          <el-table-column prop="description" label="描述" min-width="120" show-overflow-tooltip>
            <template #default="{ row }">{{ row.description || '—' }}</template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openWorkSiteDialog(row, proj.project_id)">编辑</el-button>
              <el-popconfirm title="确认删除该工点？" @confirm="doDeleteWorkSite(row.site_id, proj.project_id)">
                <template #reference>
                  <el-button link type="danger" size="small">删除</el-button>
                </template>
              </el-popconfirm>
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>
    </el-collapse>

    <!-- ── Project 对话框 ── -->
    <el-dialog v-model="projDialog.visible" :title="projDialog.id ? '编辑工程' : '新增工程'"
      width="480px" destroy-on-close>
      <el-form ref="projFormRef" :model="projDialog.form" :rules="projRules" label-width="90px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="projDialog.form.name" />
        </el-form-item>
        <el-form-item label="类型">
          <el-select v-model="projDialog.form.type" clearable style="width:100%">
            <el-option v-for="t in PROJECT_TYPES" :key="t.value" :label="t.label" :value="t.value" />
          </el-select>
        </el-form-item>
        <el-form-item label="默认坐标系">
          <el-input v-model="projDialog.form.default_crs" placeholder="EPSG:4547" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="projDialog.form.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="projDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="projDialog.saving" @click="saveProject">保存</el-button>
      </template>
    </el-dialog>

    <!-- ── WorkSite 对话框 ── -->
    <el-dialog v-model="wsDialog.visible" :title="wsDialog.id ? '编辑工点' : '新增工点'"
      width="560px" destroy-on-close>
      <el-form ref="wsFormRef" :model="wsDialog.form" :rules="wsRules" label-width="100px">
        <el-row :gutter="16">
          <el-col :span="14">
            <el-form-item label="名称" prop="name">
              <el-input v-model="wsDialog.form.name" />
            </el-form-item>
          </el-col>
          <el-col :span="10">
            <el-form-item label="类型">
              <el-select v-model="wsDialog.form.type" clearable style="width:100%">
                <el-option v-for="t in WS_TYPES" :key="t" :label="t" :value="t" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="10">
            <el-form-item label="里程冠号">
              <el-input v-model="wsDialog.form.mileage_prefix" placeholder="如 X1DK、ZDK" clearable />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="施工方向">
          <el-radio-group v-model="wsDialog.form.construction_direction">
            <el-radio-button value="forward">大里程（forward）</el-radio-button>
            <el-radio-button value="backward">小里程（backward）</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="起始里程(m)">
              <el-input-number v-model="wsDialog.form.start_mileage" :controls="false" style="width:100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="终止里程(m)">
              <el-input-number v-model="wsDialog.form.end_mileage" :controls="false" style="width:100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item label="中线数据">
          <el-select v-model="wsDialog.form.centerline_id" clearable filterable
            placeholder="仅显示 ECL 类型数据集" style="width:100%"
            :loading="wsDialog.loadingDatasets">
            <el-option
              v-for="ds in wsDialog.centerlineOptions"
              :key="ds.id"
              :label="ds.name"
              :value="ds.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="断面轮廓">
          <el-select v-model="wsDialog.form.profile_id" clearable filterable
            placeholder="仅显示 PRF 类型数据集" style="width:100%"
            :loading="wsDialog.loadingDatasets">
            <el-option
              v-for="ds in wsDialog.profileOptions"
              :key="ds.id"
              :label="ds.name"
              :value="ds.id"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="wsDialog.form.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="wsDialog.visible = false">取消</el-button>
        <el-button type="primary" :loading="wsDialog.saving" @click="saveWorkSite">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  listProjects, createProject, updateProject, deleteProject,
  listWorkSites, createWorkSite, updateWorkSite, deleteWorkSite,
  listDatasets,
} from '../api/index.js'

// ── 枚举 ──────────────────────────────────────────────────────────────────────
const PROJECT_TYPES = [
  { value: 'highway',    label: '公路（highway）'    },
  { value: 'railway',    label: '铁路（railway）'    },
  { value: 'metro',      label: '地铁（metro）'      },
  { value: 'municipal',  label: '市政（municipal）'  },
  { value: 'waterway',   label: '水路（waterway）'   },
]
const WS_TYPES = ['正洞', '平导', '斜井', '横洞', '洞门', '明洞']

// ── state ─────────────────────────────────────────────────────────────────────
const loadingProjects    = ref(false)
const projects           = ref([])
const openPanels         = ref([])
const workSitesByProject = reactive({})
const loadingWorkSites   = reactive({})
// 按工程缓存：ECL 中线列表 / PRF 断面列表（用于表格显示名称 + 对话框下拉）
const eclByProject       = reactive({})   // { [projectId]: Dataset[] }
const prfByProject       = reactive({})   // { [projectId]: Dataset[] }

// ── 工具函数：根据 dataset_id 显示名称（从两个缓存中查找）────────────────────
function datasetName(datasetId, projectId) {
  const all = [...(eclByProject[projectId] || []), ...(prfByProject[projectId] || [])]
  return all.find(d => d.id === datasetId)?.name ?? datasetId
}

// ── 数据加载 ──────────────────────────────────────────────────────────────────
async function loadProjects() {
  loadingProjects.value = true
  try {
    const res = await listProjects({ size: 100 })
    projects.value = res.items
  } finally { loadingProjects.value = false }
}

async function loadWorkSites(projectId) {
  if (loadingWorkSites[projectId]) return
  loadingWorkSites[projectId] = true
  try {
    const res = await listWorkSites({ project_id: projectId, size: 100 })
    workSitesByProject[projectId] = res.items
  } finally { loadingWorkSites[projectId] = false }
}

async function loadTypedDatasets(projectId) {
  if (eclByProject[projectId] && prfByProject[projectId]) return
  const eclRes = await listDatasets(
    { project_id: projectId, data_type: 'ECL', size: 100 }
  )
  const prfRes = await listDatasets(
    { project_id: projectId, data_type: 'PRF', size: 100 }
  )
  eclByProject[projectId] = eclRes.items
  prfByProject[projectId] = prfRes.items
}

async function onCollapseChange(activeNames) {
  for (const pid of activeNames) {
    await loadWorkSites(pid)
    await loadTypedDatasets(pid)
  }
}

onMounted(loadProjects)

// ── Project CRUD ──────────────────────────────────────────────────────────────
const projFormRef = ref()
const projRules   = { name: [{ required: true, message: '请输入工程名称' }] }
const projDialog  = reactive({
  visible: false, saving: false, id: null,
  form: { name: '', type: '', default_crs: 'EPSG:4547', description: '' },
})

function openProjectDialog(proj = null) {
  projDialog.id = proj?.project_id ?? null
  Object.assign(projDialog.form, proj
    ? { name: proj.name, type: proj.type || '', default_crs: proj.default_crs || 'EPSG:4547', description: proj.description || '' }
    : { name: '', type: '', default_crs: 'EPSG:4547', description: '' })
  projDialog.visible = true
}

async function saveProject() {
  await projFormRef.value.validate()
  projDialog.saving = true
  try {
    if (projDialog.id) {
      await updateProject(projDialog.id, projDialog.form)
      ElMessage.success('更新成功')
    } else {
      await createProject(projDialog.form)
      ElMessage.success('创建成功')
    }
    projDialog.visible = false
    await loadProjects()
  } finally { projDialog.saving = false }
}

async function doDeleteProject(id) {
  await deleteProject(id)
  ElMessage.success('已删除')
  delete workSitesByProject[id]
  delete eclByProject[id]
  delete prfByProject[id]
  await loadProjects()
}

// ── WorkSite CRUD ─────────────────────────────────────────────────────────────
const wsFormRef = ref()
const wsRules   = { name: [{ required: true, message: '请输入工点名称' }] }
const wsDialog  = reactive({
  visible: false, saving: false, id: null, projectId: null,
  loadingDatasets: false,
  centerlineOptions: [],   // ECL 类型数据集
  profileOptions:    [],   // PRF 类型数据集
  form: {
    name: '', type: '', mileage_prefix: '',
    construction_direction: null,
    centerline_id: null, profile_id: null,
    start_mileage: null, end_mileage: null, description: '',
  },
})

async function openWorkSiteDialog(ws = null, projectId) {
  wsDialog.id        = ws?.site_id ?? null
  wsDialog.projectId = projectId
  Object.assign(wsDialog.form, ws
    ? {
        name: ws.name, type: ws.type || '',
        mileage_prefix: ws.mileage_prefix || '',
        construction_direction: ws.construction_direction || null,
        centerline_id: ws.centerline_id || null,
        profile_id:    ws.profile_id    || null,
        start_mileage: ws.start_mileage ?? null,
        end_mileage:   ws.end_mileage   ?? null,
        description:   ws.description   || '',
      }
    : {
        name: '', type: '', mileage_prefix: '',
        construction_direction: null,
        centerline_id: null, profile_id: null,
        start_mileage: null, end_mileage: null, description: '',
      })

  // 填充下拉选项：优先使用缓存，否则并行拉取
  if (eclByProject[projectId] && prfByProject[projectId]) {
    wsDialog.centerlineOptions = eclByProject[projectId]
    wsDialog.profileOptions    = prfByProject[projectId]
  } else {
    wsDialog.loadingDatasets = true
    try {
      const eclRes = await listDatasets(
        { project_id: projectId, data_type: 'ECL', size: 100 }
      )
      const prfRes = await listDatasets(
        { project_id: projectId, data_type: 'PRF', size: 100 }
      )
      eclByProject[projectId] = eclRes.items
      prfByProject[projectId] = prfRes.items
      wsDialog.centerlineOptions = eclRes.items
      wsDialog.profileOptions    = prfRes.items
    } finally { wsDialog.loadingDatasets = false }
  }

  wsDialog.visible = true
}

async function saveWorkSite() {
  await wsFormRef.value.validate()
  wsDialog.saving = true
  try {
    const body = {
      ...wsDialog.form,
      project_id: wsDialog.projectId,
    }
    if (wsDialog.id) {
      const res = await updateWorkSite(wsDialog.id, body)
      if (res?.site_id) wsDialog.id = res.site_id
      ElMessage.success('更新成功')
    } else {
      await createWorkSite(body)
      ElMessage.success('创建成功')
    }
    wsDialog.visible = false
    // 清缓存，重新加载
    delete workSitesByProject[wsDialog.projectId]
    await loadWorkSites(wsDialog.projectId)
  } finally { wsDialog.saving = false }
}

async function doDeleteWorkSite(siteId, projectId) {
  await deleteWorkSite(siteId)
  ElMessage.success('已删除')
  delete workSitesByProject[projectId]
  await loadWorkSites(projectId)
}
</script>

<style scoped>
.page-header { display:flex; justify-content:space-between; align-items:center; margin-bottom:16px; }
.page-title  { font-size:20px; font-weight:600; color:#1a2332; }

.collapse-title {
  display: flex;
  align-items: center;
  gap: 10px;
  flex: 1;
  min-width: 0;
}
.type-tag  { flex-shrink: 0; }
.proj-name { font-weight: 600; font-size: 14px; }
.proj-meta { font-size: 12px; color: #909399; }
.collapse-actions { margin-left: auto; display: flex; gap: 4px; flex-shrink: 0; }
.text-muted { color: #c0c4cc; }
</style>
