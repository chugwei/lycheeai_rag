<template>
  <div class="flex h-full">
    <!-- ─── 会话列表侧栏 ─── -->
    <aside
      class="flex w-60 flex-col border-r border-slate-200 bg-white transition-all duration-200"
      :class="showSidebar ? 'w-60' : 'w-0 overflow-hidden border-r-0'"
    >
      <!-- 侧栏头部 -->
      <div class="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <span class="text-sm font-medium text-slate-700">会话历史</span>
        <el-button size="small" type="primary" text :icon="Plus" @click="newConversation">
          新建
        </el-button>
      </div>

      <!-- 会话列表 -->
      <div class="flex-1 overflow-y-auto px-2 py-2">
        <div v-if="!conversations.length" class="py-8 text-center text-xs text-slate-400">
          暂无会话记录
        </div>
        <div
          v-for="conv in conversations"
          :key="conv.id"
          class="group relative mb-1 cursor-pointer rounded-lg px-3 py-2.5 text-sm transition-colors"
          :class="conv.id === currentConvId ? 'bg-brand-50 text-brand-700' : 'text-slate-600 hover:bg-slate-50'"
          @click="switchConversation(conv.id)"
        >
          <div class="truncate text-sm font-medium">{{ conv.title || '新对话' }}</div>
          <div class="mt-0.5 text-[11px] text-slate-400">{{ formatConvTime(conv.createdAt) }}</div>
          <!-- 删除按钮 -->
          <el-button
            size="small"
            circle
            text
            type="danger"
            class="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 transition-opacity group-hover:opacity-100"
            @click.stop="deleteConversation(conv.id)"
          >
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
      </div>

      <!-- 侧栏底部 -->
      <div class="border-t border-slate-100 px-4 py-2 text-xs text-slate-400">
        {{ conversations.length }} 个对话
      </div>
    </aside>

    <!-- ─── 主聊天区 ─── -->
    <div class="flex flex-1 flex-col bg-slate-50">
      <!-- 顶栏 -->
      <header class="flex min-h-14 items-center justify-between border-b border-slate-200 bg-white px-4 py-3">
        <div class="flex items-center gap-3">
          <el-button size="small" text class="text-slate-500" @click="showSidebar = !showSidebar">
            <el-icon><Operation /></el-icon>
          </el-button>
          <el-icon class="text-brand-600"><ChatDotSquare /></el-icon>
          <h2 class="text-base font-semibold text-slate-800">智能问答</h2>
        </div>
        <div class="flex items-center gap-4">
          <!-- LLM 后端切换器 -->
          <div class="flex items-center gap-2 text-xs">
            <span class="text-slate-400">LLM:</span>
            <el-select
              v-model="selectedBackend"
              size="small"
              class="w-28"
              @change="handleBackendChange"
            >
              <el-option label="本地GPU" value="openai" />
              <el-option label="外部API" value="external" />
              <el-option label="Ollama" value="ollama" />
            </el-select>
            <el-tooltip content="配置外部 API" placement="bottom">
              <el-button v-if="selectedBackend === 'external'" size="small" circle text class="text-slate-400 hover:text-brand-600" @click="openConfigDialog">
                <el-icon><Setting /></el-icon>
              </el-button>
            </el-tooltip>
          </div>
          <span class="rounded-full px-2.5 py-0.5 text-[11px] font-medium" :class="backendStatusClass">
            {{ loading ? '思考中...' : backendStatusLabel }}
          </span>
        </div>
      </header>

      <!-- 外部 LLM 配置弹窗 -->
      <el-dialog v-model="configVisible" title="配置外部 LLM" width="480px" append-to-body>
        <el-form label-position="top">
          <el-form-item label="API 地址 (OpenAI 兼容格式)">
            <el-input v-model="configForm.base_url" placeholder="https://token.sensenova.cn/v1" />
          </el-form-item>
          <el-form-item label="API 密钥">
            <el-input v-model="configForm.api_key" type="password" show-password placeholder="sk-..." />
          </el-form-item>
          <el-form-item label="模型名称">
            <el-input v-model="configForm.model" placeholder="deepseek-v4-flash / gpt-4o-mini / qwen-turbo" />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="configVisible = false">取消</el-button>
          <el-button type="primary" :loading="configLoading" @click="handleSaveConfig">保存并切换</el-button>
        </template>
      </el-dialog>

      <!-- 来源预览弹窗 -->
      <el-dialog v-model="sourcePreviewVisible" :title="sourcePreviewTitle" width="min(800px, 90vw)" append-to-body>
        <div class="max-h-[60vh] overflow-auto rounded bg-slate-50 p-4">
          <pre v-if="sourcePreviewContent" class="whitespace-pre-wrap text-sm leading-6 text-slate-700">{{ sourcePreviewContent }}</pre>
          <div v-else class="py-8 text-center text-slate-400">无法加载该文件内容</div>
        </div>
      </el-dialog>

      <!-- 消息区 -->
      <main ref="chatRef" class="min-h-0 flex-1 overflow-y-auto px-6 py-5">
        <section v-if="!messages.length" class="flex h-full items-center justify-center">
          <div class="w-full max-w-2xl text-center">
            <div class="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-50 text-3xl text-brand-600">
              🍒
            </div>
            <h1 class="mt-5 text-2xl font-semibold text-slate-900">今天想了解什么？</h1>
            <p class="mt-2 text-sm text-slate-500">向荔知君提问，系统会结合荔枝种植知识库生成答案。</p>
            <div class="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <button
                v-for="suggestion in suggestions"
                :key="suggestion"
                type="button"
                class="rounded-lg border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-700 transition-colors hover:border-brand-500 hover:text-brand-700"
                @click="askSuggestion(suggestion)"
              >
                {{ suggestion }}
              </button>
            </div>
          </div>
        </section>

        <section v-else class="mx-auto max-w-4xl space-y-5">
          <article
            v-for="(msg, index) in messages"
            :key="index"
            :class="['flex', msg.role === 'user' ? 'justify-end' : 'justify-start']"
          >
            <div
              :class="[
                'max-w-[85%] rounded-xl px-4 py-3 shadow-sm',
                msg.role === 'user' ? 'bg-brand-600 text-white' : 'border border-slate-200 bg-white text-slate-700',
              ]"
            >
              <div v-if="msg.role === 'assistant'" class="mb-2 flex items-center gap-2 text-xs text-slate-500">
                <el-icon><MagicStick /></el-icon>
                <span>荔知君</span>
              </div>
              <div class="whitespace-pre-wrap text-sm leading-6">{{ msg.content }}</div>
              <div v-if="msg.meta" class="mt-2 flex items-center gap-3 border-t border-slate-100 pt-2 text-xs text-slate-400">
                <span>意图：{{ msg.meta.intent }} · 置信度：{{ (msg.meta.confidence * 100).toFixed(0) }}%</span>
                <span v-if="msg.meta.latency" class="text-slate-300">|</span>
                <span v-if="msg.meta.latency">⏱ {{ msg.meta.latency.toFixed(2) }}s</span>
              </div>
              <!-- 引用来源 -->
              <div v-if="msg.sources?.length" class="mt-2 border-t border-slate-100 pt-2">
                <div class="mb-1 text-xs text-slate-400">📚 引用来源：</div>
                <div class="flex flex-wrap gap-1.5">
                  <button
                    v-for="src in msg.sources"
                    :key="src.ref_id"
                    type="button"
                    class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs transition-colors hover:border-brand-300 hover:bg-brand-50"
                    :class="relevanceTagClass(src.rerank_score)"
                    @click="previewSource(src)"
                  >
                    <span class="font-medium">[{{ src.ref_id }}]</span>
                    <span class="opacity-70">{{ relevanceLabel(src.rerank_score) }}</span>
                  </button>
                </div>
              </div>
            </div>
          </article>

          <article v-if="loading" class="flex justify-start">
            <div class="max-w-[85%] rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
              <div class="mb-2 flex items-center gap-2 text-xs text-slate-500">
                <el-icon class="animate-spin"><Loading /></el-icon>
                <span>荔知君正在思考...</span>
              </div>
            </div>
          </article>
        </section>
      </main>

      <!-- 输入区 -->
      <footer class="border-t border-slate-200 bg-white p-4">
        <div class="mx-auto max-w-4xl">
          <div class="flex items-end gap-3 rounded-xl border border-slate-200 bg-white p-3 focus-within:border-brand-300 focus-within:ring-1 focus-within:ring-brand-200">
            <el-input
              v-model="question"
              type="textarea"
              :rows="2"
              resize="none"
              :disabled="loading"
              placeholder="输入荔枝种植问题，Enter 发送"
              class="flex-1"
              @keydown.enter="handleEnter"
            />
            <el-button type="primary" :loading="loading" :disabled="!question.trim() || loading" @click="sendMessage">
              发送
            </el-button>
          </div>
        </div>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { onBeforeRouteLeave } from 'vue-router'
import { ChatDotSquare, MagicStick, Loading, Setting, Plus, Delete, Operation } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { queryChat, getLLMConfig, setLLMConfig, previewKnowledgeFile, getChunkDetail } from '@/api/lychee'

const suggestions = [
  '荔枝花穗太多怎么处理？',
  '霜疫霉病怎么防治？',
  '蒂蛀虫什么时候防治效果最好？',
  '桂味荔枝有什么特点？',
]

// ─── 外部 LLM 配置持久化 ───
const EXTERNAL_CONFIG_KEY = 'lycheeai_external_llm_config'
const CONVERSATIONS_KEY = 'lycheeai_conversations'
const DEFAULT_EXTERNAL_CONFIG = {
  base_url: 'https://token.sensenova.cn/v1',
  api_key: '',
  model: 'deepseek-v4-flash',
}

function restoreExternalConfig() {
  try {
    const saved = localStorage.getItem(EXTERNAL_CONFIG_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      configForm.value = { ...DEFAULT_EXTERNAL_CONFIG, ...parsed }
      return true
    }
  } catch { /* ignore */ }
  return false
}

function persistExternalConfig() {
  localStorage.setItem(EXTERNAL_CONFIG_KEY, JSON.stringify({
    base_url: configForm.value.base_url,
    api_key: configForm.value.api_key,
    model: configForm.value.model,
  }))
}

// ─── 会话管理 ───
const showSidebar = ref(true)
const conversations = ref([])
const currentConvId = ref('')

function generateConvId() {
  return 'conv_' + Date.now() + '_' + Math.random().toString(36).slice(2, 6)
}

function loadConversations() {
  try {
    const saved = localStorage.getItem(CONVERSATIONS_KEY)
    if (saved) {
      conversations.value = JSON.parse(saved)
    }
  } catch { conversations.value = [] }
}

function saveConversations() {
  try {
    localStorage.setItem(CONVERSATIONS_KEY, JSON.stringify(conversations.value))
  } catch { /* ignore */ }
}

function getCurrentConversation() {
  return conversations.value.find(c => c.id === currentConvId.value)
}

function newConversation() {
  const conv = {
    id: generateConvId(),
    title: '新对话',
    messages: [],
    createdAt: new Date().toISOString(),
  }
  conversations.value.unshift(conv)
  currentConvId.value = conv.id
  messages.value = []
  saveConversations()
}

function switchConversation(convId) {
  const conv = conversations.value.find(c => c.id === convId)
  if (!conv) return
  // 先保存当前会话
  saveCurrentConversation()
  currentConvId.value = convId
  messages.value = conv.messages || []
}

function deleteConversation(convId) {
  const idx = conversations.value.findIndex(c => c.id === convId)
  if (idx === -1) return
  conversations.value.splice(idx, 1)
  saveConversations()
  if (currentConvId.value === convId) {
    // 切换到下一个可用会话，或新建
    if (conversations.value.length > 0) {
      switchConversation(conversations.value[0].id)
    } else {
      newConversation()
    }
  }
}

function saveCurrentConversation() {
  const conv = getCurrentConversation()
  if (!conv) return
  conv.messages = messages.value
  // 根据第一条用户消息自动生成标题
  if (conv.title === '新对话' && messages.value.length > 0) {
    const firstUserMsg = messages.value.find(m => m.role === 'user')
    if (firstUserMsg) {
      conv.title = firstUserMsg.content.slice(0, 30) + (firstUserMsg.content.length > 30 ? '...' : '')
    }
  }
  saveConversations()
}

function formatConvTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  const now = new Date()
  const diff = now - d
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return Math.floor(diff / 60000) + '分钟前'
  if (diff < 86400000) return Math.floor(diff / 3600000) + '小时前'
  return d.toLocaleDateString('zh-CN', { month: 'numeric', day: 'numeric' })
}

// ─── 聊天状态 ───
const question = ref('')
const messages = ref([])
const loading = ref(false)
const chatRef = ref(null)
const selectedBackend = ref('external')
const configVisible = ref(false)
const configLoading = ref(false)
const backendActive = ref('openai')
const backendModel = ref('')

const configForm = ref({ ...DEFAULT_EXTERNAL_CONFIG })

const backendStatusClass = computed(() => {
  if (backendActive.value === 'mock') return 'bg-red-100 text-red-700'
  return 'bg-brand-50 text-brand-700'
})

const backendStatusLabel = computed(() => {
  const map = {
    openai: '本地GPU · ' + (backendModel.value || 'Qwen3.5-4B'),
    external: '外部API · ' + (backendModel.value || 'configured'),
    ollama: 'Ollama · ' + (backendModel.value || 'running'),
    mock: '离线模式',
  }
  return map[backendActive.value] || backendActive.value
})

onMounted(async () => {
  restoreExternalConfig()
  // 恢复会话历史
  loadConversations()
  if (conversations.value.length > 0) {
    currentConvId.value = conversations.value[0].id
    messages.value = conversations.value[0].messages || []
  } else {
    newConversation()
  }

  try {
    const { data } = await getLLMConfig()
    selectedBackend.value = data.backend === 'external' ? 'external' : data.backend === 'ollama' ? 'ollama' : 'openai'
    backendActive.value = data.active_backend
    backendModel.value = data.model || ''
  } catch {
    // 默认使用外部 API
  }
})

// 监听消息变化，自动保存当前会话
watch(messages, () => {
  saveCurrentConversation()
}, { deep: true })

// 导航离开时，如果正在生成则保存当前会话并警告
onBeforeRouteLeave((to, from, next) => {
  saveCurrentConversation()
  if (loading.value) {
    ElMessage.warning('正在生成回答，切换页面将中断请求')
  }
  next()
})

async function handleBackendChange(backend) {
  await switchBackend(backend)
}

function openConfigDialog() {
  restoreExternalConfig()
  configVisible.value = true
}

async function handleSaveConfig() {
  configLoading.value = true
  try {
    const payload = { backend: 'external' }
    if (configForm.value.base_url) payload.base_url = configForm.value.base_url
    if (configForm.value.api_key) payload.api_key = configForm.value.api_key
    if (configForm.value.model) payload.model = configForm.value.model
    persistExternalConfig()
    await switchBackend('external', payload)
    configVisible.value = false
  } catch (error) {
    ElMessage.error('配置保存失败')
  } finally {
    configLoading.value = false
  }
}

async function switchBackend(backend, extraPayload = null) {
  const prevBackend = backendActive.value
  const prevSelected = selectedBackend.value
  try {
    const payload = extraPayload || { backend }
    const { data } = await setLLMConfig(payload)
    if (data.active_backend === 'mock') {
      if (backend === 'openai') {
        ElMessage.warning('本地 GPU 推理服务未启动，请先运行 python scripts/openai_server.py')
      } else if (backend === 'ollama') {
        ElMessage.warning('Ollama 服务未启动，请先运行 ollama serve')
      } else {
        ElMessage.warning('外部 API 不可用，请检查 API 密钥和地址是否正确')
      }
      if (prevBackend && prevBackend !== 'mock') {
        try {
          await setLLMConfig({ backend: prevBackend })
          const { data: rollback } = await getLLMConfig()
          backendActive.value = rollback.active_backend
          backendModel.value = rollback.model || ''
        } catch {
          backendActive.value = 'mock'
          backendModel.value = ''
        }
      } else {
        backendActive.value = 'mock'
        backendModel.value = ''
      }
      selectedBackend.value = prevSelected
      return
    }
    backendActive.value = data.active_backend
    backendModel.value = data.model || ''
    ElMessage.success(`已切换至 ${data.active_backend === 'openai' ? '本地GPU' : data.active_backend === 'external' ? '外部API' : data.active_backend === 'ollama' ? 'Ollama' : data.active_backend}`)
  } catch (error) {
    ElMessage.error('切换失败，请检查后端服务是否正常运行')
    selectedBackend.value = prevSelected
  }
}

function handleEnter(e) {
  if (e.shiftKey) return
  e.preventDefault()
  sendMessage()
}

function askSuggestion(text) {
  question.value = text
  sendMessage()
}

async function sendMessage() {
  const text = question.value.trim()
  if (!text || loading.value) return

  messages.value.push({ role: 'user', content: text })
  question.value = ''
  loading.value = true
  scrollToBottom()

  try {
    const { data } = await queryChat({ query: text })
    messages.value.push({
      role: 'assistant',
      content: data.answer,
      meta: {
        intent: data.intent,
        confidence: data.confidence,
        latency: data.latency,
      },
      sources: data.sources || [],
    })
  } catch (error) {
    if (backendActive.value === 'external' || backendActive.value === 'mock') {
      ElMessageBox.confirm(
        '外部 API 请求失败，是否修改 API 配置？',
        'API 错误',
        {
          confirmButtonText: '去配置',
          cancelButtonText: '取消',
          type: 'error',
          distinguishCancelAndClose: true,
        }
      ).then(() => {
        openConfigDialog()
      }).catch(() => {})
    } else {
      ElMessage.error('问答请求失败，请检查后端服务')
    }
  } finally {
    loading.value = false
    scrollToBottom()
  }
}

function scrollToBottom() {
  nextTick(() => {
    chatRef.value?.scrollTo({ top: chatRef.value.scrollHeight, behavior: 'smooth' })
  })
}

// ─── 来源预览 ───
const sourcePreviewVisible = ref(false)
const sourcePreviewTitle = ref('')
const sourcePreviewContent = ref('')

function relevanceLabel(score) {
  if (!score || score <= 0) return ''
  if (score >= 0.8) return '高相关'
  if (score >= 0.5) return '中相关'
  return '低相关'
}

function relevanceTagClass(score) {
  if (!score || score <= 0) return 'border-slate-200 bg-slate-50 text-slate-500'
  if (score >= 0.8) return 'border-green-200 bg-green-50 text-green-700'
  if (score >= 0.5) return 'border-amber-200 bg-amber-50 text-amber-700'
  return 'border-slate-200 bg-slate-50 text-slate-500'
}

async function previewSource(src) {
  sourcePreviewTitle.value = `[${src.ref_id}] ${src.source}`
  sourcePreviewContent.value = ''
  sourcePreviewVisible.value = true

  // 尝试通过 chunk_id 获取完整分块内容
  if (src.chunk_id) {
    try {
      const { data } = await getChunkDetail(src.chunk_id)
      let text = `【分块 ID】${src.chunk_id}\n`
      text += `【来源文件】${data.metadata?.source || src.source}\n`
      text += `【知识类型】${data.metadata?.knowledge_type || '-'}\n`
      if (src.rerank_score > 0) {
        text += `【相关度分数】${(src.rerank_score * 100).toFixed(1)}%\n`
      }
      if (src.retrieval_paths?.length) {
        text += `【检索路径】${src.retrieval_paths.join(' + ')}\n`
      }
      text += `\n【完整内容】\n${data.content || src.text_preview || '(无内容)'}`
      sourcePreviewContent.value = text
      return
    } catch {
      // chunk 详情获取失败，降级到文本预览
    }
  }

  // 降级：显示文本预览
  let text = `【引用片断】\n${src.text_preview || '(无内容)'}\n`
  if (src.chunk_id) {
    text += `\n【分块 ID】${src.chunk_id}\n`
  }
  if (src.retrieval_paths?.length) {
    text += `\n【检索路径】${src.retrieval_paths.join(' + ')}`
  }
  try {
    const { data } = await previewKnowledgeFile(src.source)
    text += `\n\n【完整文件】\n${data.content}`
  } catch {}
  sourcePreviewContent.value = text
}
</script>

<style scoped>
:deep(.el-textarea__inner) {
  border: none;
  box-shadow: none;
  padding: 0;
  background: transparent;
}
</style>
