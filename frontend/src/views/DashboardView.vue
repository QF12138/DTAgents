<template>
  <div>
    <h2 class="page-title">数据概览</h2>

    <!-- 统计卡片 (2行×3列) -->
    <el-row :gutter="16" class="stats-row">
      <el-col :span="8" v-for="card in statCards" :key="card.key">
        <div class="stat-card" :style="{ borderTopColor: card.color }">
          <div class="stat-left">
            <div class="stat-label">{{ card.label }}</div>
            <div class="stat-value">{{ stats[card.key] ?? '…' }}</div>
          </div>
          <el-icon class="stat-icon" :style="{ color: card.color }">
            <component :is="card.icon" />
          </el-icon>
        </div>
      </el-col>
    </el-row>

    <!-- 快速入口 -->
    <el-card shadow="never" class="quick-card">
      <template #header><span class="card-title">快速入口</span></template>
      <div class="quick-links">
        <router-link v-for="link in quickLinks" :key="link.to" :to="link.to">
          <el-button :type="link.type" plain size="large">
            <el-icon><component :is="link.icon" /></el-icon>
            {{ link.label }}
          </el-button>
        </router-link>
      </div>
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { getStats } from '../api/index.js'

const stats = ref({})

onMounted(async () => {
  stats.value = await getStats()
})

const statCards = [
  { key: 'projects',           label: '工程',     icon: 'FolderOpened', color: '#409eff' },
  { key: 'centerlines',        label: '中线',     icon: 'Connection',   color: '#67c23a' },
  { key: 'work_sites',         label: '工点',     icon: 'MapLocation',  color: '#e6a23c' },
  { key: 'datasets',           label: '数据集',   icon: 'Files',        color: '#9b59b6' },
  { key: 'processing_history', label: '处理历史', icon: 'Histogram',    color: '#f56c6c' },
  { key: 'model_registry',     label: '地质模型', icon: 'Box',          color: '#00bcd4' },
]

const quickLinks = [
  { to: '/hierarchy', label: '工程层级', icon: 'Grid',        type: 'primary' },
  { to: '/datasets',  label: '管理数据集', icon: 'Files',     type: 'success' },
  { to: '/history',   label: '查看历史', icon: 'Histogram',   type: 'warning' },
  { to: '/models',    label: '管理模型', icon: 'Box',         type: 'info'    },
]
</script>

<style scoped>
.page-title { font-size: 20px; font-weight: 600; color: #1a2332; margin-bottom: 20px; }

.stats-row { margin-bottom: 20px; row-gap: 16px; }

.stat-card {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  border-top: 3px solid transparent;
  box-shadow: 0 1px 6px rgba(0,0,0,.06);
  margin-bottom: 0;
}
.stat-label { font-size: 13px; color: #909399; margin-bottom: 6px; }
.stat-value { font-size: 30px; font-weight: 700; color: #1a2332; }
.stat-icon { font-size: 36px; opacity: .2; }

.card-title { font-weight: 600; }
.quick-card { border-radius: 8px; }
.quick-links { display: flex; gap: 12px; flex-wrap: wrap; }
.quick-links a { text-decoration: none; }
</style>
