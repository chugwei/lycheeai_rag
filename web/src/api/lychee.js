import axios from 'axios'

const request = axios.create({
  baseURL: '/api',
  timeout: 180000,
})

// 问答
export function queryChat(data) {
  return request.post('/query', data)
}

export function queryChatWithImage(formData) {
  return request.post('/query/image', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

// 图像识别
export function analyzeImage(formData) {
  return request.post('/image/analyze', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
}

// 预测
export function predictRisk(data) {
  return request.post('/predict', data)
}

// 健康检查
export function healthCheck() {
  return request.get('/health')
}

// 知识库文件管理
export function listKnowledgeFiles(search = '') {
  return request.get('/knowledge/files', { params: { search } })
}

export function uploadKnowledgeFile(file) {
  const formData = new FormData()
  formData.append('file', file)
  return request.post('/knowledge/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function deleteKnowledgeFile(filename) {
  return request.delete(`/knowledge/files/${encodeURIComponent(filename)}`)
}

export function batchDeleteKnowledgeFiles(filenames) {
  return request.post('/knowledge/files/batch-delete', { filenames })
}

export function downloadKnowledgeFile(filename) {
  return request.get(`/knowledge/files/${encodeURIComponent(filename)}/download`, {
    responseType: 'blob',
  })
}

export function batchDownloadKnowledgeFiles(filenames) {
  return request.post('/knowledge/files/batch-download', { filenames }, {
    responseType: 'blob',
  })
}

export function previewKnowledgeFile(filename) {
  return request.get(`/knowledge/files/${encodeURIComponent(filename)}/content`)
}

// LLM 配置管理
export function getLLMConfig() {
  return request.get('/llm/config')
}

export function setLLMConfig(data) {
  return request.post('/llm/config', data)
}

// 分块数据浏览
export function getChunks(params = {}) {
  return request.get('/chunks', { params })
}

export function getChunkDetail(chunkId) {
  return request.get(`/chunks/${encodeURIComponent(chunkId)}`)
}

export function updateChunk(chunkId, data, token) {
  return request.put(`/chunks/${encodeURIComponent(chunkId)}`, data, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
}

// 管理员登录
export function adminLogin(data) {
  return request.post('/auth/login', data)
}

// 通用下载工具
export function downloadBlob(blob, filename) {
  const url = window.URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  window.URL.revokeObjectURL(url)
}
