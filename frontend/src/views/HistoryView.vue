<template>
  <div>
    <div class="page-header">
      <h2 class="page-title">处理历史</h2>
    </div>

    <el-card shadow="never" class="filter-card">
      <el-form inline :model="filters">
        <el-form-item label="工程">
          <el-select v-model="filters.project_id" placeholder="全部" clearable style="width:150px">
            <el-option v-for="p in projectOptions" :key="p.id" :label="p.name" :value="p.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="智能体">
          <el-input v-model="filters.agent_name" placeholder="模糊搜索" clearable style="width:180px" />
        </el-form-item>
        <el-form-item label="状态">
          <el-select v-model="filters.status" placeholder="全部" clearable style="width:130px">
            <el-option label="pending（等待）"  value="pending"  />
            <el-option label="running（运行中）" value="running"  />
            <el-option label="success（成功）"  value="success"  />
            <el-option label="failed（失败）"   value="failed"   />
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
        <el-table-column prop="id"           label="ID"       width="70"  align="center" />
        <el-table-column prop="project_id"   label="工程"     width="140" show-overflow-tooltip>
          <template #default="{ row }">
            {{ projectName(row.project_id) }}
          </template>
        </el-table-column>
        <el-table-column prop="agent_name"   label="智能体"   width="180" show-overflow-tooltip />
        <el-table-column prop="tool_name"    label="工具"     width="180" show-overflow-tooltip />
        <el-table-column prop="status"       label="状态"     width="100">
          <template #default="{ row }">
            <el-tag size="small" :type="statusType(row.status)">{{ row.status }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="duration_ms"  label="耗时(ms)" width="90" align="right" />
        <el-table-column prop="error_message" label="错误信息" min-width="200" show-overflow-tooltip />
        <el-table-column prop="created_at"   label="创建时间"  width="160" />
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ row }">
            <el-popconfirm title="确认删除此条记录？" @confirm="doDelete(row.id)">
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
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { listHistory, deleteHistory, listProjects } from '../api/index.js'

const loading = ref(false)
const rows    = ref([])
const total   = ref(0)
const page    = ref(1)
const size    = ref(20)
const filters = reactive({ project_id: '', agent_name: '', status: '' })

const projectOptions = ref([])
const projectMap     = computed(() => Object.fromEntries(projectOptions.value.map(p => [p.id, p.name])))
const projectName    = id => projectMap.value[id] ?? id ?? '—'

const statusType = s => ({ pending:'info', running:'warning', success:'success', failed:'danger' }[s] ?? '')

async function fetchData() {
  loading.value = true
  try {
    const params = { page: page.value, size: size.value }
    if (filters.project_id) params.project_id = filters.project_id
    if (filters.agent_name) params.agent_name = filters.agent_name
    if (filters.status)     params.status     = filters.status
    const res = await listHistory(params)
    rows.value  = res.items
    total.value = res.total
  } finally { loading.value = false }
}

async function loadProjectOptions() {
  const res = await listProjects({ size: 50 })
  projectOptions.value = res.items
}

function resetFilters() {
  Object.assign(filters, { project_id: '', agent_name: '', status: '' })
  page.value = 1
  fetchData()
}

async function doDelete(id) {
  await deleteHistory(id)
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
