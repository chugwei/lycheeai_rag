<template>
  <div class="flex h-full flex-col bg-slate-50">
    <header class="flex min-h-14 items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
      <div class="flex items-center gap-2">
        <el-icon class="text-brand-600"><FolderOpened /></el-icon>
        <h2 class="text-base font-semibold text-slate-800">荔枝知识库</h2>
      </div>
      <div class="flex items-center gap-4 text-xs text-slate-500">
        <el-tag size="small" type="info" effect="plain">{{ dbTypeLabel }}</el-tag>
      </div>
    </header>

    <!-- Tab 切换 -->
    <div class="border-b border-slate-200 bg-white px-6">
      <el-tabs v-model="activeTab" class="knowledge-tabs">
        <el-tab-pane label="📄 文件管理" name="files" />
        <el-tab-pane label="🧩 分块数据" name="chunks" />
      </el-tabs>
    </div>

    <main class="min-h-0 flex-1 overflow-hidden p-6">
      <!-- ──────── 文件管理 ──────── -->
      <div v-if="activeTab === 'files'" class="mx-auto flex h-full max-w-7xl flex-col gap-5">
        <!-- 工具栏 -->
        <div class="flex flex-col gap-4 rounded-xl border border-slate-200 bg-white p-4 sm:flex-row sm:items-center sm:justify-between">
          <div class="flex flex-1 items-center gap-3">
            <el-input
              v-model="searchKeyword"
              placeholder="按文件名搜索"
              clearable
              class="w-full sm:w-80"
              @keyup.enter="handleSearch"
            >
              <template #prefix>
                <el-icon><Search /></el-icon>
              </template>
            </el-input>
            <el-button type="primary" :icon="Search" @click="handleSearch">搜索</el-button>
          </div>

          <div class="flex items-center gap-3">
            <el-upload
              :show-file-list="false"
              :before-upload="handleUpload"
              accept=".md,.txt,.pdf,.doc,.docx"
            >
              <el-button type="primary" :icon="Upload" :loading="uploading">上传文件</el-button>
            </el-upload>

            <el-button
              :icon="Download"
              :disabled="!selectedFiles.length"
              @click="handleBatchDownload"
            >
              批量下载
            </el-button>
            <el-button
              type="danger"
              :icon="Delete"
              :disabled="!selectedFiles.length"
              @click="handleBatchDelete"
            >
              批量删除
            </el-button>
          </div>
        </div>

        <!-- 表格 -->
        <el-card shadow="never" class="flex-1 overflow-hidden border border-slate-200">
          <el-table
            v-loading="loading"
            :data="fileList"
            @selection-change="handleSelectionChange"
            height="100%"
            stripe
          >
            <el-table-column type="selection" width="55" />
            <el-table-column type="index" label="序号" width="80" align="center" />
            <el-table-column prop="name" label="文件名" min-width="200" show-overflow-tooltip>
              <template #default="{ row }">
                <div class="flex items-center gap-2">
                  <el-icon class="text-slate-400"><Document /></el-icon>
                  <span class="text-sm text-slate-700">{{ row.name }}</span>
                </div>
              </template>
            </el-table-column>
            <el-table-column prop="size" label="大小" width="120">
              <template #default="{ row }">
                <span class="text-xs text-slate-500">{{ formatSize(row.size) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="upload_time" label="上传时间" width="180">
              <template #default="{ row }">
                <span class="text-xs text-slate-500">{{ formatDate(row.upload_time) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="update_time" label="更新时间" width="180">
              <template #default="{ row }">
                <span class="text-xs text-slate-500">{{ formatDate(row.update_time) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="220" fixed="right">
              <template #default="{ row }">
                <div class="flex items-center gap-2">
                  <el-button link type="primary" :icon="View" @click="handlePreview(row)">预览</el-button>
                  <el-button link type="primary" :icon="Download" @click="handleDownload(row)">下载</el-button>
                  <el-popconfirm title="确定删除该文件吗？" confirm-button-text="删除" cancel-button-text="取消" @confirm="handleDelete(row)">
                    <template #reference>
                      <el-button link type="danger" :icon="Delete">删除</el-button>
                    </template>
                  </el-popconfirm>
                </div>
              </template>
            </el-table-column>
            <template #empty>
              <div class="py-12 text-slate-400">
                <el-icon class="text-4xl"><FolderOpened /></el-icon>
                <div class="mt-2 text-sm">暂无文件，请上传</div>
              </div>
            </template>
          </el-table>
        </el-card>
      </div><!-- /.文件管理 -->

      <!-- ──────── 分块数据 ──────── -->
      <div v-if="activeTab === 'chunks'" class="mx-auto flex h-full max-w-7xl flex-col gap-4">
        <!-- 过滤工具栏 -->
        <div class="flex flex-wrap items-center gap-3 rounded-xl border border-slate-200 bg-white p-4">
          <el-input
            v-model="chunkSearch"
            placeholder="搜索分块内容"
            clearable
            class="w-60"
            @keyup.enter="fetchChunks"
          >
            <template #prefix><el-icon><Search /></el-icon></template>
          </el-input>
          <el-select v-model="chunkTypeFilter" placeholder="知识类型" clearable class="w-36" @change="fetchChunks">
            <el-option label="全部" value="" />
            <el-option label="病虫害" value="disease_pest" />
            <el-option label="农事指导" value="agronomy" />
            <el-option label="物候期" value="phenology" />
            <el-option label="品种" value="variety" />
            <el-option label="监测" value="monitoring" />
            <el-option label="通用" value="general" />
          </el-select>
          <el-button type="primary" :icon="Refresh" @click="fetchChunks">刷新</el-button>
          <span class="ml-auto text-xs text-slate-400">共 {{ chunkTotal }} 条分块</span>
        </div>

        <!-- 分块列表 -->
        <el-card shadow="never" class="flex-1 overflow-hidden border border-slate-200">
          <el-table
            v-loading="chunkLoading"
            :data="chunkList"
            height="100%"
            stripe
            size="small"
          >
            <el-table-column type="index" label="#" width="50" align="center" />
            <el-table-column prop="chunk_id" label="分块ID" width="200" show-overflow-tooltip>
              <template #default="{ row }">
                <el-button link type="primary" class="text-xs" @click="openChunkDetail(row)">{{ row.chunk_id }}</el-button>
              </template>
            </el-table-column>
            <el-table-column prop="content" label="内容（前500字）" min-width="300" show-overflow-tooltip>
              <template #default="{ row }">
                <div class="line-clamp-3 text-xs leading-5 text-slate-700 cursor-pointer hover:text-brand-600" @click="openChunkDetail(row)">{{ row.content }}</div>
              </template>
            </el-table-column>
            <el-table-column prop="source" label="来源文件" width="150" show-overflow-tooltip />
            <el-table-column prop="knowledge_type" label="知识类型" width="110">
              <template #default="{ row }">
                <el-tag :type="typeTag(row.knowledge_type)" size="small" effect="plain">{{ row.knowledge_type }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="phenology_stages" label="物候期" width="140" show-overflow-tooltip>
              <template #default="{ row }">
                <span class="text-xs text-slate-500">{{ row.phenology_stages?.join(', ') || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="risk_level" label="风险" width="80" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.risk_level === '高'" type="danger" size="small">高</el-tag>
                <el-tag v-else-if="row.risk_level === '中'" type="warning" size="small">中</el-tag>
                <el-tag v-else size="info" effect="plain">低</el-tag>
              </template>
            </el-table-column>
            <template #empty>
              <div class="py-12 text-center text-slate-400">
                <el-icon class="text-3xl"><FolderOpened /></el-icon>
                <div class="mt-2 text-sm">暂无分块数据，请先构建索引</div>
              </div>
            </template>
          </el-table>
        </el-card>

        <!-- 分页 -->
        <div class="flex justify-center">
          <el-pagination
            v-model:current-page="chunkPage"
            :page-size="chunkPageSize"
            :total="chunkTotal"
            layout="prev, pager, next"
            small
            @current-change="fetchChunks"
          />
        </div>
      </div>
    </main>

    <!-- 预览弹窗（文件管理） -->
    <el-dialog v-model="previewVisible" :title="previewTitle" width="min(900px, 90vw)" append-to-body>
      <div class="max-h-[70vh] overflow-auto rounded bg-slate-50 p-4">
        <pre v-if="previewContent" class="whitespace-pre-wrap text-sm leading-6 text-slate-700">{{ previewContent }}</pre>
        <div v-else class="py-8 text-center text-slate-400">无法预览该文件</div>
      </div>
    </el-dialog>

    <!-- 管理员登录弹窗 -->
    <el-dialog v-model="loginVisible" title="管理员验证" width="400px" append-to-body>
      <el-form label-position="top" @keyup.enter="handleLogin">
        <el-form-item label="用户名">
          <el-input v-model="loginForm.username" placeholder="admin" />
        </el-form-item>
        <el-form-item label="密码">
          <el-input v-model="loginForm.password" type="password" show-password placeholder="输入密码" @keyup.enter="handleLogin" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="loginVisible = false">取消</el-button>
        <el-button type="primary" :loading="loginLoading" @click="handleLogin">登录</el-button>
      </template>
    </el-dialog>

    <!-- 分块详情/编辑弹窗 -->
    <el-dialog v-model="chunkDetailVisible" :title="'分块详情 - ' + (chunkDetail?.chunk_id || '')" width="min(900px, 90vw)" append-to-body>
      <template v-if="chunkDetail">
        <div class="mb-4 flex items-center justify-between">
          <div class="flex items-center gap-2 text-xs text-slate-400">
            <span>来源: {{ chunkDetail.metadata?.source || '-' }}</span>
            <span>|</span>
            <span>类型: {{ chunkDetail.metadata?.knowledge_type || '-' }}</span>
            <span>|</span>
            <span>风险: {{ chunkDetail.metadata?.risk_level || '-' }}</span>
          </div>
          <el-switch :model-value="chunkEditing" active-text="编辑" inactive-text="查看" @change="(v) => v ? requireAdmin() : chunkEditing = false" />
        </div>

        <div v-if="!chunkEditing" class="max-h-[60vh] overflow-auto rounded bg-slate-50 p-4">
          <pre class="whitespace-pre-wrap text-sm leading-6 text-slate-700">{{ chunkDetail.content }}</pre>
        </div>

        <div v-else>
          <el-form label-position="top" size="small">
            <el-form-item label="完整内容">
              <el-input v-model="editForm.content" type="textarea" :rows="12" />
            </el-form-item>
            <el-form-item label="来源文件">
              <el-input v-model="editForm.source" />
            </el-form-item>
            <el-form-item label="知识类型">
              <el-select v-model="editForm.knowledge_type" class="w-full">
                <el-option label="病虫害" value="disease_pest" />
                <el-option label="农事指导" value="agronomy" />
                <el-option label="物候期" value="phenology" />
                <el-option label="品种" value="variety" />
                <el-option label="监测" value="monitoring" />
                <el-option label="通用" value="general" />
              </el-select>
            </el-form-item>
            <el-form-item label="风险等级">
              <el-select v-model="editForm.risk_level" class="w-full">
                <el-option label="高" value="高" />
                <el-option label="中" value="中" />
                <el-option label="低" value="低" />
              </el-select>
            </el-form-item>
            <el-form-item label="物候期（逗号分隔）">
              <el-input v-model="editForm.phenology_stages" placeholder="如: 开花期,幼果期" />
            </el-form-item>
            <el-form-item label="实体（逗号分隔）">
              <el-input v-model="editForm.entities" placeholder="如: 霜疫霉病,荔枝" />
            </el-form-item>
          </el-form>
        </div>
      </template>
      <template #footer>
        <el-button @click="chunkDetailVisible = false">关闭</el-button>
        <el-button v-if="chunkEditing" type="primary" :loading="chunkSaving" @click="handleSaveChunk">保存修改</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, watch, onMounted } from 'vue'
import {
  FolderOpened, Search, Upload, Download, Delete, View, Document, Refresh,
} from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  listKnowledgeFiles,
  uploadKnowledgeFile,
  deleteKnowledgeFile,
  batchDeleteKnowledgeFiles,
  downloadKnowledgeFile,
  batchDownloadKnowledgeFiles,
  previewKnowledgeFile,
  getChunks,
  getChunkDetail,
  updateChunk,
  adminLogin,
  healthCheck,
  downloadBlob,
} from '@/api/lychee'

// ─── Tab ───
const activeTab = ref('files')
const dbTypeLabel = ref('ChromaDB')

// ─── 文件管理 ───
const loading = ref(false)
const uploading = ref(false)
const searchKeyword = ref('')
const fileList = ref([])
const selectedFiles = ref([])
const previewVisible = ref(false)
const previewTitle = ref('')
const previewContent = ref('')

// ─── 分块数据 ───
const chunkLoading = ref(false)
const chunkList = ref([])
const chunkTotal = ref(0)
const chunkPage = ref(1)
const chunkPageSize = ref(50)
const chunkSearch = ref('')
const chunkTypeFilter = ref('')

onMounted(async () => {
  fetchFiles()
  // 获取向量库类型用于显示
  try {
    const hd = await healthCheck()
    if (hd?.data?.vector_db_status) dbTypeLabel.value = hd.data.vector_db_status
  } catch {}
})

// 切换到分块Tab时自动加载
watch(activeTab, (tab) => {
  if (tab === 'chunks') {
    chunkPage.value = 1
    fetchChunks()
  }
})

// ─── 文件管理方法 ───
async function fetchFiles() {
  loading.value = true
  try {
    const { data } = await listKnowledgeFiles(searchKeyword.value)
    fileList.value = data
  } catch (error) {
    ElMessage.error('获取文件列表失败')
  } finally {
    loading.value = false
  }
}

function handleSearch() { fetchFiles() }
function handleSelectionChange(selection) { selectedFiles.value = selection }

async function handleUpload(file) {
  const allowed = ['.md', '.txt', '.pdf', '.doc', '.docx']
  const ext = file.name.slice(file.name.lastIndexOf('.')).toLowerCase()
  if (!allowed.includes(ext)) {
    ElMessage.error('仅支持 .md、.txt、.pdf、.doc、.docx 文件')
    return false
  }
  uploading.value = true
  try {
    await uploadKnowledgeFile(file)
    ElMessage.success('上传成功')
    fetchFiles()
  } catch {
    ElMessage.error('上传失败')
  } finally {
    uploading.value = false
  }
  return false
}

async function handleDownload(row) {
  try {
    const { data } = await downloadKnowledgeFile(row.name)
    downloadBlob(data, row.name)
  } catch { ElMessage.error('下载失败') }
}

async function handleDelete(row) {
  try {
    await deleteKnowledgeFile(row.name)
    ElMessage.success('删除成功')
    fetchFiles()
  } catch { ElMessage.error('删除失败') }
}

async function handleBatchDownload() {
  if (!selectedFiles.value.length) return
  try {
    const filenames = selectedFiles.value.map(f => f.name)
    const { data } = await batchDownloadKnowledgeFiles(filenames)
    downloadBlob(data, 'lychee-knowledge-files.zip')
  } catch { ElMessage.error('批量下载失败') }
}

async function handleBatchDelete() {
  if (!selectedFiles.value.length) return
  try {
    await ElMessageBox.confirm(
      `确定删除选中的 ${selectedFiles.value.length} 个文件吗？`,
      '批量删除',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' }
    )
  } catch { return }
  try {
    const filenames = selectedFiles.value.map(f => f.name)
    await batchDeleteKnowledgeFiles(filenames)
    ElMessage.success('批量删除成功')
    selectedFiles.value = []
    fetchFiles()
  } catch { ElMessage.error('批量删除失败') }
}

async function handlePreview(row) {
  previewTitle.value = row.name
  previewContent.value = ''
  previewVisible.value = true
  try {
    const { data } = await previewKnowledgeFile(row.name)
    previewContent.value = data.content
  } catch { ElMessage.error('预览失败') }
}

// ─── 分块方法 ───
async function fetchChunks() {
  chunkLoading.value = true
  try {
    const params = {
      page: chunkPage.value,
      page_size: chunkPageSize.value,
    }
    if (chunkSearch.value) params.search = chunkSearch.value
    if (chunkTypeFilter.value) params.knowledge_type = chunkTypeFilter.value

    const { data } = await getChunks(params)
    chunkList.value = data.chunks || []
    chunkTotal.value = data.total || 0
  } catch { ElMessage.error('获取分块数据失败') }
  finally { chunkLoading.value = false }
}

function typeTag(type) {
  const map = { disease_pest: 'danger', agronomy: 'success', phenology: 'warning', variety: 'primary', monitoring: 'info' }
  return map[type] || 'info'
}

// ─── 管理员验证 ───
const loginVisible = ref(false)
const loginLoading = ref(false)
const adminToken = ref(localStorage.getItem('lycheeai_admin_token') || '')
const loginForm = ref({ username: 'admin', password: '' })

async function handleLogin() {
  loginLoading.value = true
  try {
    const { data } = await adminLogin({
      username: loginForm.value.username || 'admin',
      password: loginForm.value.password,
    })
    adminToken.value = data.token
    localStorage.setItem('lycheeai_admin_token', data.token)
    loginVisible.value = false
    ElMessage.success('登录成功')
    // 登录后直接进入编辑模式
    chunkEditing.value = true
  } catch {
    ElMessage.error('用户名或密码错误')
  } finally {
    loginLoading.value = false
  }
}

function requireAdmin() {
  if (adminToken.value) {
    // 已有令牌，尝试进入编辑
    chunkEditing.value = true
  } else {
    loginVisible.value = true
  }
}

// ─── 分块详情/编辑 ───
const chunkDetailVisible = ref(false)
const chunkEditing = ref(false)
const chunkSaving = ref(false)
const chunkDetail = ref(null)
const editForm = ref({
  content: '',
  source: '',
  knowledge_type: '',
  risk_level: '低',
  phenology_stages: '',
  entities: '',
})

async function openChunkDetail(row) {
  chunkEditing.value = false
  chunkDetail.value = null
  chunkDetailVisible.value = true
  try {
    const { data } = await getChunkDetail(row.chunk_id)
    chunkDetail.value = data
    // 兼容 metadata 中 phenology_stages/entities 可能是字符串或数组
    const stages = data.metadata?.phenology_stages
    const ents = data.metadata?.entities
    editForm.value = {
      content: data.content || '',
      source: data.metadata?.source || '',
      knowledge_type: data.metadata?.knowledge_type || '',
      risk_level: data.metadata?.risk_level || '低',
      phenology_stages: Array.isArray(stages) ? stages.join(', ') : (stages || ''),
      entities: Array.isArray(ents) ? ents.join(', ') : (ents || ''),
    }
  } catch { ElMessage.error('获取分块详情失败') }
}

async function handleSaveChunk() {
  chunkSaving.value = true
  try {
    await updateChunk(chunkDetail.value.chunk_id, {
      content: editForm.value.content,
      metadata: {
        source: editForm.value.source,
        knowledge_type: editForm.value.knowledge_type,
        risk_level: editForm.value.risk_level,
        phenology_stages: editForm.value.phenology_stages.split(',').map(s => s.trim()).filter(Boolean),
        entities: editForm.value.entities.split(',').map(s => s.trim()).filter(Boolean),
      },
    }, adminToken.value)
    ElMessage.success('保存成功')
    chunkDetailVisible.value = false
    chunkEditing.value = false
    fetchChunks()
  } catch (e) {
    if (e?.response?.status === 401) {
      ElMessage.error('登录已过期，请重新登录')
      adminToken.value = ''
      localStorage.removeItem('lycheeai_admin_token')
      loginVisible.value = true
    } else {
      ElMessage.error('保存失败')
    }
  }
  finally { chunkSaving.value = false }
}

function formatSize(bytes) {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i]
}

function formatDate(iso) {
  if (!iso) return '-'
  const d = new Date(iso)
  return isNaN(d.getTime()) ? iso : d.toLocaleString('zh-CN')
}
</script>

<style scoped>
:deep(.el-table) {
  --el-table-header-bg-color: #f8fafc;
}
:deep(.el-table th) {
  font-weight: 600;
  color: #475569;
}
</style>
