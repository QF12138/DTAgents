<template>
  <div class="layout">
    <!-- 侧边栏 -->
    <aside class="sidebar">
      <div class="logo">
        <span class="logo-icon">🗄️</span>
        <span class="logo-text">DTAgents</span>
      </div>
      <el-menu
        :default-active="activeMenu"
        router
        class="side-menu"
        background-color="#1a2332"
        text-color="#a0aec0"
        active-text-color="#ffffff"
      >
        <el-menu-item index="/dashboard">
          <el-icon><DataAnalysis /></el-icon>
          <span>数据概览</span>
        </el-menu-item>
        <el-menu-item index="/hierarchy">
          <el-icon><Grid /></el-icon>
          <span>工程层级</span>
        </el-menu-item>
        <el-menu-item index="/datasets">
          <el-icon><Files /></el-icon>
          <span>数据集</span>
        </el-menu-item>
        <el-menu-item index="/history">
          <el-icon><Histogram /></el-icon>
          <span>处理历史</span>
        </el-menu-item>
        <el-menu-item index="/models">
          <el-icon><Box /></el-icon>
          <span>地质模型</span>
        </el-menu-item>
      </el-menu>
    </aside>

    <!-- 主区域 -->
    <div class="main-wrap">
      <header class="topbar">
        <el-breadcrumb separator="/">
          <el-breadcrumb-item :to="{ path: '/' }">首页</el-breadcrumb-item>
          <el-breadcrumb-item>{{ breadcrumb }}</el-breadcrumb-item>
        </el-breadcrumb>
      </header>
      <main class="content">
        <router-view />
      </main>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const activeMenu = computed(() => route.path)

const NAMES = {
  '/dashboard': '数据概览',
  '/hierarchy': '工程层级',
  '/datasets':  '数据集',
  '/history':   '处理历史',
  '/models':    '地质模型',
}
const breadcrumb = computed(() => NAMES[route.path] ?? '')
</script>

<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif; background: #f0f2f5; }
</style>

<style scoped>
.layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

/* ── 侧边栏 ── */
.sidebar {
  width: 220px;
  flex-shrink: 0;
  background: #1a2332;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.logo {
  height: 60px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 20px;
  border-bottom: 1px solid #243447;
}
.logo-icon { font-size: 22px; }
.logo-text { color: #fff; font-size: 17px; font-weight: 600; letter-spacing: .5px; }

.side-menu {
  flex: 1;
  border-right: none;
  padding-top: 8px;
}
.side-menu :deep(.el-menu-item) {
  height: 46px;
  line-height: 46px;
  border-radius: 6px;
  margin: 2px 10px;
  width: calc(100% - 20px);
}
.side-menu :deep(.el-menu-item.is-active) {
  background-color: #2d4a6e !important;
}
.side-menu :deep(.el-menu-item:hover) {
  background-color: #243447 !important;
}

/* ── 主区域 ── */
.main-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.topbar {
  height: 60px;
  background: #fff;
  display: flex;
  align-items: center;
  padding: 0 24px;
  box-shadow: 0 1px 4px rgba(0,0,0,.08);
  flex-shrink: 0;
}

.content {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
}
</style>
