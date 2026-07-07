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
        <div class="flex items-center gap-2 rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-500">
          <el-icon><InfoFilled /></el-icon>
          <span>服务状态：{{ serviceStatus }}</span>
        </div>
      </div>
    </el-aside>

    <el-main class="min-w-0 p-0">
      <router-view />
    </el-main>
  </el-container>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ChatDotSquare, Camera, TrendCharts, FolderOpened, InfoFilled } from '@element-plus/icons-vue'
import { healthCheck } from '@/api/lychee'

const route = useRoute()
const serviceStatus = ref('检测中...')

const activeMenu = computed(() => route.path)

async function checkHealth() {
  try {
    const { data } = await healthCheck()
    serviceStatus.value = data.llm_available ? 'LLM 可用' : 'LLM 不可用'
  } catch {
    serviceStatus.value = '后端离线'
  }
}

function handleSelect() {
  // 菜单切换时可选做额外处理
}

onMounted(() => {
  checkHealth()
  setInterval(checkHealth, 30000)
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
