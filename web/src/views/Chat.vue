<template>
  <div class="flex h-full">
    <!-- ─── 会话列表侧栏 ─── -->
    <aside
      class="flex w-60 flex-col border-r border-slate-200 bg-white transition-all duration-200"
      :class="showSidebar ? 'w-60' : 'w-0 overflow-hidden border-r-0'"
    >
      <div class="flex items-center justify-between border-b border-slate-100 px-4 py-3">
        <span class="text-sm font-medium text-slate-700">会话历史</span>
        <el-button size="small" type="primary" text :icon="Plus" @click="newConversation">新建</el-button>
      </div>

      <div class="flex-1 overflow-y-auto px-2 py-2">
        <div v-if="!conversations.length" class="py-8 text-center text-xs text-slate-400">暂无会话记录</div>
        <div
          v-for="conv in conversations" :key="conv.id"
          class="group relative mb-1 cursor-pointer rounded-lg px-3 py-2.5 text-sm transition-colors"
          :class="conv.id === currentConvId ? 'bg-brand-50 text-brand-700' : 'text-slate-600 hover:bg-slate-50'"
          @click="switchConversation(conv.id)"
        >
          <div class="truncate text-sm font-medium">{{ conv.title || '新对话' }}</div>
          <div class="mt-0.5 text-[11px] text-slate-400">{{ formatConvTime(conv.createdAt) }}</div>
          <el-button size="small" circle text type="danger"
            class="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 transition-opacity group-hover:opacity-100"
            @click.stop="deleteConversation(conv.id)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
      </div>

      <div class="border-t border-slate-100 px-4 py-2 space-y-1">
        <div class="text-xs text-slate-400">{{ conversations.length }} 个对话</div>
        <el-button v-if="conversations.length > 1" size="small" text type="danger" class="text-xs"
          @click="clearAllConversations">
          清空所有会话
        </el-button>
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
          <div class="flex items-center gap-2 text-xs">
            <span class="text-slate-400">LLM:</span>
            <el-select v-model="selectedBackend" size="small" class="w-28" @change="handleBackendChange">
              <el-option label="本地GPU" value="openai" />
              <el-option label="外部API" value="external" />
              <el-option label="Ollama" value="ollama" />
            </el-select>
            <el-tooltip content="配置外部 API" placement="bottom">
              <el-button v-if="selectedBackend === 'external'"
                size="small" circle text class="text-slate-400 hover:text-brand-600"
                @click="openConfigDialog">
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
          <el-form-item label="extra_body (JSON，可选)">
            <el-input v-model="configForm.extra_body" placeholder='{"enable_thinking": false}' :rows="2" type="textarea" />
            <div class="mt-1 text-xs text-slate-400">不同模型需要的额外参数，deepseek-v4-flash 可填 {"enable_thinking": false} 来加速</div>
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
            <div class="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-50 text-3xl text-brand-600">🍒</div>
            <h1 class="mt-5 text-2xl font-semibold text-slate-900">今天想了解什么？</h1>
            <p class="mt-2 text-sm text-slate-500">向荔知君提问，系统会结合荔枝种植知识库生成答案。</p>
            <div class="mt-6 grid grid-cols-1 gap-3 sm:grid-cols-2">
              <button v-for="s in suggestions" :key="s" type="button"
                class="rounded-lg border border-slate-200 bg-white px-4 py-3 text-left text-sm text-slate-700 transition-colors hover:border-brand-500 hover:text-brand-700"
                @click="askSuggestion(s)">{{ s }}</button>
            </div>
          </div>
        </section>

        <section v-else class="mx-auto max-w-4xl space-y-5">
          <article v-for="(msg, idx) in messages" :key="msg.id || idx"
            :class="['flex', msg.role === 'user' ? 'justify-end' : 'justify-start']">
            <div :class="[
              'max-w-[85%] rounded-xl px-4 py-3 shadow-sm',
              msg.role === 'user' ? 'bg-brand-600 text-white' : 'border border-slate-200 bg-white text-slate-700',
            ]">
              <div v-if="msg.role === 'assistant'" class="mb-2 flex items-center gap-2 text-xs text-slate-500">
                <el-icon><MagicStick /></el-icon><span>荔知君</span>
              </div>

              <!-- 消息正文：Markdown 渲染（assistant）或纯文本（user） -->
              <div v-if="msg.role === 'assistant'" class="markdown-body text-sm leading-6"
                v-html="renderMarkdown(msg.content)"></div>
              <div v-else class="whitespace-pre-wrap text-sm leading-6">{{ msg.content }}</div>

              <!-- 元数据 -->
              <div v-if="msg.meta?.latency != null"
                class="mt-2 flex items-center gap-3 border-t border-slate-100 pt-2 text-xs text-slate-400">
                <span>意图：{{ msg.meta.intent }} · 置信度：{{ (msg.meta.confidence * 100).toFixed(0) }}%</span>
                <span class="text-slate-300">|</span>
                <span>⏱ {{ msg.meta.latency.toFixed(2) }}s</span>
              </div>

              <!-- 引用来源 -->
              <div v-if="msg.sources?.length" class="mt-2 border-t border-slate-100 pt-2">
                <div class="mb-1 text-xs text-slate-400">📚 引用来源：</div>
                <div class="flex flex-wrap gap-1.5">
                  <button v-for="src in msg.sources" :key="src.ref_id" type="button"
                    class="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs transition-colors hover:border-brand-300 hover:bg-brand-50"
                    :class="relevanceTagClass(src.rerank_score)"
                    @click="previewSource(src)">
                    <span class="font-medium">[{{ src.ref_id }}]</span>
                    <span class="opacity-70">{{ relevanceLabel(src.rerank_score) }}</span>
                  </button>
                </div>
              </div>

              <!-- 操作按钮（仅 assistant） -->
              <div v-if="msg.role === 'assistant'" class="mt-2 flex items-center gap-2 border-t border-slate-100 pt-2">
                <el-button size="small" text class="text-xs text-slate-400 hover:text-brand-600"
                  @click="copyMessage(msg.content)">
                  📋 复制
                </el-button>
                <el-button size="small" text class="text-xs text-slate-400 hover:text-brand-600"
                  @click="regenerateMessage(msg)">
                  🔄 重新生成
                </el-button>
              </div>
            </div>
          </article>

          <!-- 流式加载指示器 -->
          <article v-if="loading" class="flex justify-start">
            <div class="max-w-[85%] rounded-xl border border-slate-200 bg-white px-4 py-3 shadow-sm">
              <div class="mb-2 flex items-center gap-2 text-xs text-slate-500">
                <el-icon class="animate-spin"><Loading /></el-icon>
                <span v-if="streamingPhase === 'retrieving'">正在检索知识库...</span>
                <span v-else-if="streamingPhase === 'thinking'">
                  正在思考...
                  <span v-if="streamingSources.length" class="text-slate-400">
                    （📚 已检索到 {{ streamingSources.length }} 条相关文档）
                  </span>
                </span>
                <span v-else>正在准备...</span>
              </div>
            </div>
          </article>
        </section>
      </main>

      <!-- 输入区 -->
      <footer class="border-t border-slate-200 bg-white p-4">
        <div class="mx-auto max-w-4xl">
          <div class="flex items-end gap-3 rounded-xl border border-slate-200 bg-white p-3 focus-within:border-brand-300 focus-within:ring-1 focus-within:ring-brand-200">
            <el-input v-model="question" type="textarea" :rows="2" resize="none" :disabled="loading"
              placeholder="输入荔枝种植问题，Enter 发送" class="flex-1" @keydown.enter="handleEnter" />
            <div class="flex gap-1">
              <el-button v-if="loading" type="danger" @click="abortStream">
                <el-icon><Close /></el-icon> 停止
              </el-button>
              <el-button v-else type="primary" :disabled="!question.trim()" @click="sendMessageStream">
                发送
              </el-button>
            </div>
          </div>
        </div>
      </footer>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { onBeforeRouteLeave } from 'vue-router'
import { ChatDotSquare, MagicStick, Loading, Setting, Plus, Delete, Operation, Close } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { queryChat, queryChatStream, getLLMConfig, setLLMConfig, previewKnowledgeFile, getChunkDetail } from '@/api/lychee'
import { marked } from 'marked'
import DOMPurify from 'dompurify'

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
    extra_body: configForm.value.extra_body,
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
    if (saved) conversations.value = JSON.parse(saved)
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
    if (conversations.value.length > 0) {
      switchConversation(conversations.value[0].id)
    } else {
      newConversation()
    }
  }
}

function clearAllConversations() {
  conversations.value = []
  saveConversations()
  newConversation()
  ElMessage.success('已清空所有会话')
}

function saveCurrentConversation() {
  const conv = getCurrentConversation()
  if (!conv) return
  conv.messages = messages.value
  if (conv.title === '新对话' && messages.value.length > 0) {
    const firstUserMsg = messages.value.find(m => m.role === 'user')
    if (firstUserMsg) conv.title = firstUserMsg.content.slice(0, 30) + (firstUserMsg.content.length > 30 ? '...' : '')
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

// ─── Markdown 渲染 ───
function renderMarkdown(text) {
  if (!text) return ''
  const raw = marked.parse(text, { breaks: true, gfm: true })
  return DOMPurify.sanitize(raw)
}

// ─── 复制 ───
async function copyMessage(text) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败')
  }
}

// ─── 聊天状态 ───
const question = ref('')
const messages = ref([])
const loading = ref(false)
const streamingPhase = ref('')
const streamingSources = ref([])
const abortController = ref(null)
const chatRef = ref(null)
const selectedBackend = ref('external')
const configVisible = ref(false)
const configLoading = ref(false)
const backendActive = ref('openai')
const backendModel = ref('')

const configForm = ref({ ...DEFAULT_EXTERNAL_CONFIG, extra_body: '' })

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
    if (data.extra_body) configForm.value.extra_body = data.extra_body
  } catch { /* default */ }
})

onUnmounted(() => {
  if (abortController.value) abortController.value.abort()
})

watch(messages, () => { saveCurrentConversation() }, { deep: true })

onBeforeRouteLeave((to, from, next) => {
  saveCurrentConversation()
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
    if (configForm.value.extra_body) payload.extra_body = configForm.value.extra_body
    persistExternalConfig()
    await switchBackend('external', payload)
    configVisible.value = false
  } catch {
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
      if (backend === 'openai') ElMessage.warning('本地 GPU 推理服务未启动，请先运行 python scripts/openai_server.py')
      else if (backend === 'ollama') ElMessage.warning('Ollama 服务未启动，请先运行 ollama serve')
      else ElMessage.warning('外部 API 不可用，请检查 API 密钥和地址是否正确')
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
  } catch {
    ElMessage.error('切换失败，请检查后端服务是否正常运行')
    selectedBackend.value = prevSelected
  }
}

function handleEnter(e) {
  if (e.shiftKey) return
  e.preventDefault()
  sendMessageStream()
}

function askSuggestion(text) {
  question.value = text
  sendMessageStream()
}

// ─── 中止流式输出 ───
function abortStream() {
  if (abortController.value) {
    abortController.value.abort()
    abortController.value = null
  }
  loading.value = false
  streamingPhase.value = ''
  ElMessage.info('已中止回答')
}

// ─── 重新生成 ───
function regenerateMessage(msg) {
  // 找到该消息之前的用户提问
  const msgIdx = messages.value.indexOf(msg)
  if (msgIdx < 1) return
  for (let i = msgIdx - 1; i >= 0; i--) {
    if (messages.value[i].role === 'user') {
      // 删除当前消息及其后面的所有消息
      messages.value.splice(msgIdx)
      question.value = messages.value[i].content
      sendMessageStream()
      return
    }
  }
}

// ─── 流式发送 ───
async function sendMessageStream() {
  const text = question.value.trim()
  if (!text || loading.value) return

  messages.value.push({ role: 'user', content: text })
  question.value = ''
  loading.value = true
  streamingPhase.value = 'retrieving'
  streamingSources.value = []
  scrollToBottom()

  // 创建 AbortController
  const controller = new AbortController()
  abortController.value = controller

  let assistantMsg = null

  try {
    const response = await queryChatStream(
      { query: text, conversation_id: currentConvId.value },
      controller.signal
    )
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    if (!response.body) throw new Error('Response body is null')
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() // 保留不完整的行

      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        const payload = line.slice(6).trim()
        if (!payload || payload === '[DONE]') continue

        try {
          const event = JSON.parse(payload)

          switch (event.type) {
            case 'sources':
              streamingPhase.value = 'thinking'
              streamingSources.value = event.data || []
              scrollToBottom()
              break

            case 'chunk':
              if (event.data.text) {
                if (!assistantMsg) {
                  const idx = messages.value.length
                  messages.value.push({ role: 'assistant', content: '', meta: {}, sources: [] })
                  assistantMsg = messages.value[idx]
                }
                assistantMsg.content += event.data.text
                scrollToBottom()
              }
              break

            case 'done':
              const d = event.data
              if (!assistantMsg) {
                const idx = messages.value.length
                messages.value.push({ role: 'assistant', content: d.answer || '', meta: {}, sources: [] })
                assistantMsg = messages.value[idx]
              }
              assistantMsg.content = d.answer || assistantMsg.content
              assistantMsg.meta = { intent: d.intent, confidence: d.confidence, latency: d.latency }
              assistantMsg.sources = d.sources || assistantMsg.sources
              // 更新 conversation_id（后端可能生成新的）
              if (d.conversation_id) currentConvId.value = d.conversation_id
              break

            case 'error':
              ElMessage.error(event.data.message || '流式响应出错')
              break
          }
        } catch { /* skip parse errors */ }
      }
    }
  } catch (error) {
    if (error.name === 'AbortError') {
      // 用户主动中止，不需要错误提示
    } else {
      ElMessage.error('流式问答失败，请检查后端服务')
      if (assistantMsg && !assistantMsg.content) {
        const idx = messages.value.indexOf(assistantMsg)
        if (idx !== -1) messages.value.splice(idx, 1)
      }
    }
  } finally {
    loading.value = false
    streamingPhase.value = ''
    streamingSources.value = []
    abortController.value = null
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

  if (src.chunk_id) {
    try {
      const { data } = await getChunkDetail(src.chunk_id)
      let text = `【分块 ID】${src.chunk_id}\n【来源文件】${data.metadata?.source || src.source}\n【知识类型】${data.metadata?.knowledge_type || '-'}\n`
      if (src.rerank_score > 0) text += `【相关度分数】${(src.rerank_score * 100).toFixed(1)}%\n`
      if (src.retrieval_paths?.length) text += `【检索路径】${src.retrieval_paths.join(' + ')}\n`
      text += `\n【完整内容】\n${data.content || src.text_preview || '(无内容)'}`
      sourcePreviewContent.value = text
      return
    } catch { /* fallback */ }
  }

  let text = `【引用片断】\n${src.text_preview || '(无内容)'}\n`
  if (src.chunk_id) text += `\n【分块 ID】${src.chunk_id}\n`
  if (src.retrieval_paths?.length) text += `\n【检索路径】${src.retrieval_paths.join(' + ')}`
  try {
    const { data } = await previewKnowledgeFile(src.source)
    text += `\n\n【完整文件】\n${data.content}`
  } catch {}
  sourcePreviewContent.value = text
}

// ─── 非流式发送（保留兼容） ───
async function sendMessage() {
  const text = question.value.trim()
  if (!text || loading.value) return
  messages.value.push({ role: 'user', content: text })
  question.value = ''
  loading.value = true
  scrollToBottom()
  try {
    const { data } = await queryChat({ query: text })
    messages.value.push({ role: 'assistant', content: data.answer, meta: { intent: data.intent, confidence: data.confidence, latency: data.latency }, sources: data.sources || [] })
  } catch (error) {
    if (backendActive.value === 'external' || backendActive.value === 'mock') {
      ElMessageBox.confirm('外部 API 请求失败，是否修改 API 配置？', 'API 错误', { confirmButtonText: '去配置', cancelButtonText: '取消', type: 'error', distinguishCancelAndClose: true }).then(() => openConfigDialog()).catch(() => {})
    } else {
      ElMessage.error('问答请求失败，请检查后端服务')
    }
  } finally {
    loading.value = false
    scrollToBottom()
  }
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

<style>
/* Markdown 渲染基础样式 */
.markdown-body h1 { font-size: 1.3em; margin: 0.6em 0 0.3em; font-weight: 600; color: #1e293b; }
.markdown-body h2 { font-size: 1.15em; margin: 0.5em 0 0.25em; font-weight: 600; color: #334155; }
.markdown-body h3 { font-size: 1.05em; margin: 0.4em 0 0.2em; font-weight: 600; color: #475569; }
.markdown-body p { margin: 0.3em 0; }
.markdown-body ul, .markdown-body ol { padding-left: 1.5em; margin: 0.3em 0; }
.markdown-body li { margin: 0.15em 0; }
.markdown-body code { background: #f1f5f9; padding: 0.15em 0.4em; border-radius: 3px; font-size: 0.9em; color: #be123c; }
.markdown-body pre { background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 6px; padding: 0.75em 1em; overflow-x: auto; margin: 0.5em 0; }
.markdown-body pre code { background: none; padding: 0; color: inherit; }
.markdown-body table { border-collapse: collapse; width: 100%; margin: 0.5em 0; font-size: 0.9em; }
.markdown-body th, .markdown-body td { border: 1px solid #e2e8f0; padding: 0.4em 0.6em; text-align: left; }
.markdown-body th { background: #f8fafc; font-weight: 600; }
.markdown-body blockquote { border-left: 3px solid #e2e8f0; margin: 0.4em 0; padding: 0.2em 0.8em; color: #64748b; }
.markdown-body strong { font-weight: 600; }
.markdown-body em { font-style: italic; }
</style>