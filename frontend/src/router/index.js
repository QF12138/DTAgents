import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/',          redirect: '/dashboard' },
  { path: '/dashboard', component: () => import('../views/DashboardView.vue') },
  { path: '/hierarchy', component: () => import('../views/HierarchyView.vue') },
  { path: '/datasets',  component: () => import('../views/DatasetsView.vue') },
  { path: '/history',   component: () => import('../views/HistoryView.vue') },
  { path: '/models',    component: () => import('../views/ModelsView.vue') },
]

export default createRouter({
  history: createWebHistory(),
  routes,
})
