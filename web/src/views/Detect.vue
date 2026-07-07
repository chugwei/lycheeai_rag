<template>
  <div class="flex h-full flex-col bg-slate-50">
    <header class="flex min-h-14 items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
      <div class="flex items-center gap-2">
        <el-icon class="text-brand-600"><Camera /></el-icon>
        <h2 class="text-base font-semibold text-slate-800">果园识病</h2>
      </div>
      <div class="text-xs text-slate-500">上传图片，AI 识别花、果实、梢枝及病虫害</div>
    </header>

    <main class="min-h-0 flex-1 overflow-y-auto p-6">
      <div class="mx-auto grid max-w-6xl grid-cols-1 gap-6 lg:grid-cols-[380px_1fr]">
        <el-card shadow="never" class="border border-slate-200">
          <template #header>
            <span class="font-medium text-slate-800">上传图片</span>
          </template>

          <div class="space-y-4">
            <el-upload
              drag
              :auto-upload="false"
              :show-file-list="false"
              :on-change="handleFileChange"
              accept="image/*"
              class="w-full"
            >
              <div class="flex flex-col items-center justify-center py-8">
                <el-icon class="text-4xl text-slate-300"><UploadFilled /></el-icon>
                <div class="mt-3 text-sm text-slate-600">点击或拖拽图片到此处</div>
                <div class="mt-1 text-xs text-slate-400">支持 jpg、png、jpeg</div>
              </div>
            </el-upload>

            <div v-if="imagePreview" class="overflow-hidden rounded-lg border border-slate-200">
              <img :src="imagePreview" alt="预览" class="h-48 w-full object-contain" />
            </div>

            <el-form label-position="top" class="mt-4">
              <el-form-item label="识别类型">
                <el-select v-model="apiType" class="w-full" placeholder="选择识别类型">
                  <el-option-group label="花果梢">
                    <el-option label="雌雄花识别" value="cixionghua" />
                    <el-option label="花穗识别" value="huasui" />
                    <el-option label="梢量识别" value="shaoliang" />
                    <el-option label="开花率" value="kaihualv" />
                    <el-option label="坐果率" value="zuoguolv" />
                    <el-option label="果实成熟度" value="guoshi" />
                    <el-option label="新梢识别" value="shao" />
                    <el-option label="白点识别" value="baidian" />
                  </el-option-group>
                  <el-option-group label="病虫害">
                    <el-option label="蒂蛀虫" value="dizhuchong" />
                  </el-option-group>
                </el-select>
              </el-form-item>

              <el-form-item label="地区编码（可选，用于蒂蛀虫）">
                <el-input v-model="cityCode" placeholder="如 441284" />
              </el-form-item>

              <el-button type="primary" class="w-full" :loading="loading" :disabled="!currentFile || loading" @click="submitDetect">
                开始识别
              </el-button>
            </el-form>
          </div>
        </el-card>

        <el-card shadow="never" class="border border-slate-200">
          <template #header>
            <span class="font-medium text-slate-800">识别结果</span>
          </template>

            <div v-if="!result" class="flex flex-col items-center justify-center py-16 text-slate-400">
              <el-icon class="text-5xl"><Camera /></el-icon>
              <div class="mt-4 text-sm">上传图片并点击识别后，结果将显示在这里</div>
            </div>

            <div v-else class="space-y-5">
              <div class="flex items-center gap-3">
                <div class="flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-xl text-brand-600">
                  ✅
                </div>
                <div>
                  <div class="text-base font-semibold text-slate-800">{{ resultTitle }}</div>
                  <div class="text-xs text-slate-500">{{ apiTypeLabel }}</div>
                </div>
              </div>

              <!-- 核心参数展示 -->
              <div v-if="coreParams.length" class="grid grid-cols-2 gap-3 sm:grid-cols-3">
                <div v-for="p in coreParams" :key="p.label"
                     class="rounded-lg border border-slate-200 bg-slate-50 p-3 text-center">
                  <div class="text-xs text-slate-500">{{ p.label }}</div>
                  <div class="mt-1 text-lg font-semibold text-brand-600">{{ p.value }}</div>
                </div>
              </div>

              <!-- LLM 分析建议 -->
              <div v-if="result.llm_analysis"
                   class="rounded-lg border border-brand-100 bg-brand-50 p-4">
                <div class="mb-2 text-sm font-semibold text-brand-700">🤖 AI 分析建议</div>
                <div class="text-sm leading-6 text-slate-700 whitespace-pre-line">{{ result.llm_analysis }}</div>
              </div>
              <div v-else-if="result.llm_analysis_error"
                   class="rounded-lg border border-amber-200 bg-amber-50 p-4">
                <div class="mb-1 text-sm font-semibold text-amber-700">⚠️ AI 分析暂不可用</div>
                <div class="text-sm text-slate-600">{{ result.llm_analysis_error }}</div>
              </div>

              <el-collapse v-model="activeCollapse" class="mt-2">
                <el-collapse-item title="查看原始数据" name="raw">
                  <pre class="max-h-80 overflow-auto rounded bg-slate-100 p-3 text-xs">{{ JSON.stringify(result, null, 2) }}</pre>
                </el-collapse-item>
              </el-collapse>
            </div>
        </el-card>
      </div>
    </main>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { Camera, UploadFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { analyzeImage } from '@/api/lychee'

const apiType = ref('guoshi')
const cityCode = ref('441284')
const currentFile = ref(null)
const imagePreview = ref('')
const loading = ref(false)
const result = ref(null)
const activeCollapse = ref([])

const apiTypeLabel = computed(() => {
  const map = {
    cixionghua: '雌雄花识别',
    huasui: '花穗识别',
    shaoliang: '梢量识别',
    kaihualv: '开花率',
    zuoguolv: '坐果率',
    guoshi: '果实成熟度',
    shao: '新梢识别',
    baidian: '白点识别',
    dizhuchong: '蒂蛀虫',
  }
  return map[apiType.value] || '图像识别'
})

const resultTitle = computed(() => {
  if (!result.value) return ''
  if (result.value.error || result.value.status === 'failed') return '识别失败'
  return '识别完成'
})

const coreParams = computed(() => {
  if (!result.value) return []
  const d = result.value
  const data = d.detection_results || d.results || d
  const list = []

  const add = (key, label, formatter) => {
    if (data[key] !== undefined && data[key] !== null && data[key] !== '') {
      list.push({ label, value: formatter ? formatter(data[key]) : data[key] })
    }
  }

  const type = apiType.value
  if (type === 'cixionghua') {
    add('male_count', '雄花数量')
    add('female_count', '雌花数量')
    add('female_ratio', '雌花比例', v => `${v}%`)
  } else if (type === 'huasui') {
    add('count', '花穗数量')
  } else if (type === 'shaoliang') {
    add('msg1', '梢量占比')
  } else if (type === 'kaihualv') {
    add('flower_rate', '开花率', v => `${v}%`)
  } else if (type === 'zuoguolv') {
    add('fruit_count', '果实个数')
  } else if (type === 'baidian') {
    add('white_spots_count', '白点数量')
  } else if (type === 'guoshi') {
    const counts = data.counts || {}
    if (typeof counts === 'object') {
      addFixed('青果', counts.green)
      addFixed('半熟果', counts.semi_ripe)
      addFixed('熟果', counts.ripe)
    }
  } else if (type === 'shao') {
    add('total_boxes', '检测梢数')
    add('avg_length', '平均长度', v => `${v} cm`)
    add('avg_thickness', '平均粗度', v => `${v} cm`)
  } else if (type === 'dizhuchong') {
    add('pupation_rate', '化蛹率', v => `${v}%`)
    add('risk_level', '风险等级')
    add('adult_count', '成虫数')
    add('cocoon_count', '茧数')
  }

  function addFixed(label, value) {
    if (value !== undefined && value !== null) {
      list.push({ label, value })
    }
  }

  return list.slice(0, 6)
})

function handleFileChange(file) {
  currentFile.value = file.raw
  imagePreview.value = URL.createObjectURL(file.raw)
}

async function submitDetect() {
  if (!currentFile.value) return
  loading.value = true
  result.value = null

  const formData = new FormData()
  formData.append('image', currentFile.value)
  formData.append('api_type', apiType.value)
  if (cityCode.value) formData.append('city_code', cityCode.value)

  try {
    const { data } = await analyzeImage(formData)
    result.value = data
  } catch (error) {
    ElMessage.error('图像识别失败，请稍后重试')
  } finally {
    loading.value = false
  }
}
</script>
