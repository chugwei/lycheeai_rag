<template>
  <el-container class="h-screen bg-slate-100">
    <el-aside width="260px" class="flex flex-col border-r border-slate-200 bg-white shadow-sm">
      <div class="flex h-20 items-center gap-3 border-b border-slate-200 px-5">
        <div class="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-brand-500 to-brand-700 text-2xl text-white shadow-sm">
          🍒
        </div>
        <div class="min-w-0">
          <div class="text-lg font-bold leading-tight tracking-tight text-slate-900">荔知君</div>
          <div class="truncate text-xs text-slate-500">荔枝种植智能助手</div>
        </div>
      </div>

      <el-menu :default-active="activeMenu" :router="true" class="flex-1 border-none py-4" @select="handleSelect">
        <el-menu-item index="/chat">
          <el-icon class="mr-3"><ChatDotSquare /></el-icon>
          <span>智能问答</span>
        </el-menu-item>
        <el-menu-item index="/detect">
          <el-icon class="mr-3"><Camera /></el-icon>
          <span>果园识病</span>
        </el-menu-item>
        <el-menu-item index="/predict">
          <el-icon class="mr-3"><TrendCharts /></el-icon>
          <span>风险预警</span>
        </el-menu-item>
        <el-menu-item index="/knowledge">
          <el-icon class="mr-3"><FolderOpened /></el-icon>
          <span>荔枝知识库</span>
        </el-menu-item>
      </el-menu>

      <div class="border-t border-slate-200 p-4">
        <div v-html="serviceStatusHTML" class="rounded-lg bg-slate-50 px-3 py-2 text-xs leading-relaxed"></div>
      </div>
    </el-aside>

    <el-main class="min-w-0 p-0">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ChatDotSquare, Camera, TrendCharts, FolderOpened } from '@element-plus/icons-vue'
import { healthCheck } from '@/api/lychee'

const route = useRoute()
const healthData = ref({ llm_available: false, vector_db_status: '', bm25_loaded: false })

const activeMenu = computed(() => route.path)

const serviceStatusHTML = computed(() => {
  const d = healthData.value
  if (!d.llm_available && !d.vector_db_status) {
    return '<span class="text-red-500">⚫ 后端离线</span>'
  }

  const llm = d.llm_available ? '🟢' : '🔴'
  const vec = d.vector_db_status ? '🟢' : '🔴'
  const bm25 = d.bm25_loaded ? '🟢' : '🔴'

  return `${llm} LLM<br>${vec} 向量库<br>${bm25} BM25`
})

let healthInterval = null

async function checkHealth() {
  try {
    const { data } = await healthCheck()
    healthData.value = {
      llm_available: data.llm_available || false,
      vector_db_status: data.vector_db_status || '',
      bm25_loaded: data.bm25_loaded || false,
    }
  } catch {
    healthData.value = { llm_available: false, vector_db_status: '', bm25_loaded: false }
  }
}

function handleSelect() {
  // 菜单切换时可选做额外处理
}

onMounted(() => {
  checkHealth()
  healthInterval = setInterval(checkHealth, 30000)
})

onUnmounted(() => {
  if (healthInterval) clearInterval(healthInterval)
})
</script>

<style scoped>
:deep(.el-menu-item) {
  height: 52px;
  margin: 4px 12px;
  padding: 0 16px !important;
  border-radius: 10px;
  font-weight: 500;
  color: #475569;
}
:deep(.el-menu-item.is-active) {
  background: #f0fdf4;
  color: #1B5E20;
  font-weight: 600;
}
:deep(.el-menu-item:hover) {
  background: #f8fafc;
}
</style>