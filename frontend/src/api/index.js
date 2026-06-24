import axios from 'axios'
import { ElMessage } from 'element-plus'

const http = axios.create({ baseURL: '/api', timeout: 15000 })

http.interceptors.response.use(
  res => res.data,
  err => {
    const msg = err.response?.data?.detail || err.message || '请求失败'
    ElMessage.error(msg)
    return Promise.reject(err)
  }
)

// ── Stats ─────────────────────────────────────────────────────────────────────
export const getStats = () => http.get('/stats')

// ── Projects ──────────────────────────────────────────────────────────────────
export const listProjects   = p        => http.get('/projects', { params: p })
export const getProject     = id       => http.get(`/projects/${id}`)
export const createProject  = b        => http.post('/projects', b)
export const updateProject  = (id, b)  => http.put(`/projects/${id}`, b)
export const deleteProject  = id       => http.delete(`/projects/${id}`)

// ── Work Sites ────────────────────────────────────────────────────────────────
export const listWorkSites   = p        => http.get('/work-sites', { params: p })
export const getWorkSite     = id       => http.get(`/work-sites/${id}`)
export const createWorkSite  = b        => http.post('/work-sites', b)
export const updateWorkSite  = (id, b)  => http.put(`/work-sites/${id}`, b)
export const deleteWorkSite  = id       => http.delete(`/work-sites/${id}`)

// ── Datasets ──────────────────────────────────────────────────────────────────
export const listDatasets   = p        => http.get('/datasets', { params: p })
export const getDataset     = id       => http.get(`/datasets/${id}`)
export const createDataset  = b        => http.post('/datasets', b)
export const updateDataset  = (id, b)  => http.put(`/datasets/${id}`, b)
export const deleteDataset  = id       => http.delete(`/datasets/${id}`)

// ── Processing History ────────────────────────────────────────────────────────
export const listHistory   = p  => http.get('/history', { params: p })
export const deleteHistory = id => http.delete(`/history/${id}`)

// ── Model Registry ────────────────────────────────────────────────────────────
export const listModels   = p        => http.get('/models', { params: p })
export const getModel     = id       => http.get(`/models/${id}`)
export const createModel  = b        => http.post('/models', b)
export const updateModel  = (id, b)  => http.put(`/models/${id}`, b)
export const deleteModel  = id       => http.delete(`/models/${id}`)
