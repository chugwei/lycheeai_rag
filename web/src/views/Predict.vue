<template>
  <div class="flex h-full flex-col bg-slate-50">
    <header class="flex min-h-14 items-center justify-between border-b border-slate-200 bg-white px-6 py-3">
      <div class="flex items-center gap-2">
        <el-icon class="text-brand-600"><TrendCharts /></el-icon>
        <h2 class="text-base font-semibold text-slate-800">风险预警</h2>
      </div>
      <div class="text-xs text-slate-500">病虫害发生风险与产量预测</div>
    </header>

    <main class="min-h-0 flex-1 overflow-y-auto p-6">
      <div class="mx-auto grid max-w-6xl grid-cols-1 gap-6 lg:grid-cols-[300px_1fr]">
        <el-card shadow="never" class="border border-slate-200">
          <template #header>
            <span class="font-medium text-slate-800">选择预测类型</span>
          </template>

          <div class="space-y-3">
            <button
              v-for="item in predictTypes"
              :key="item.value"
              type="button"
              :class="[
                'w-full rounded-lg border px-4 py-3 text-left text-sm transition-all',
                selectedType === item.value
                  ? 'border-brand-500 bg-brand-50 text-brand-700'
                  : 'border-slate-200 bg-white text-slate-600 hover:border-brand-300 hover:bg-slate-50',
              ]"
              @click="selectedType = item.value"
            >
              <div class="font-medium">{{ item.label }}</div>
              <div class="mt-1 text-xs opacity-80">{{ item.desc }}</div>
            </button>

            <el-form v-if="showCityCode" label-position="top" class="mt-4">
              <el-form-item label="城市/地区编码">
                <el-input v-model="cityCode" placeholder="如 441284" />
              </el-form-item>
            </el-form>

            <el-button type="primary" class="w-full" :loading="loading" @click="submitPredict">
              开始预测
            </el-button>
          </div>
        </el-card>

        <el-card shadow="never" class="border border-slate-200">
          <template #header>
            <span class="font-medium text-slate-800">预测结果</span>
          </template>

          <div v-if="!result" class="flex flex-col items-center justify-center py-16 text-slate-400">
            <el-icon class="text-5xl"><TrendCharts /></el-icon>
            <div class="mt-4 text-sm">选择预测类型后点击开始预测</div>
          </div>

          <div v-else-if="result.error || result.status === 'failed'" class="rounded-lg border border-red-100 bg-red-50 p-4 text-sm text-red-700">
            <div class="font-semibold">预测失败</div>
            <div class="mt-1">{{ result.error || '服务返回失败' }}</div>
          </div>

          <div v-else class="space-y-5">
            <div class="flex items-center gap-3">
              <div class="flex h-12 w-12 items-center justify-center rounded-full bg-brand-50 text-xl text-brand-600">
                📊
              </div>
              <div>
                <div class="text-base font-semibold text-slate-800">{{ currentTypeLabel }}</div>
                <div class="text-xs text-slate-500">预测已完成</div>
              </div>
            </div>

            <div v-if="riskLevel" class="rounded-lg border p-4" :class="riskClass">
              <div class="text-sm font-semibold">风险等级</div>
              <div class="mt-1 text-2xl font-bold">{{ riskLevel }}</div>
            </div>

            <div v-if="metrics.length" class="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <div v-for="m in metrics" :key="m.label" class="rounded-lg border border-slate-200 bg-slate-50 p-3 text-center">
                <div class="text-xs text-slate-500">{{ m.label }}</div>
                <div class="mt-1 text-lg font-semibold text-brand-600">{{ m.value }}</div>
              </div>
            </div>

            <div v-if="advice" class="rounded-lg border border-brand-100 bg-brand-50 p-4">
              <div class="mb-1 text-sm font-semibold text-brand-700">💡 专家建议</div>
              <div class="text-sm leading-6 text-slate-700">{{ advice }}</div>
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
import { TrendCharts } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { predictRisk } from '@/api/lychee'

const predictTypes = [
  { value: 'chunxiang', label: '椿象风险', desc: '预测荔枝椿象发生风险', showCity: true },
  { value: 'shuangyimeibing', label: '霜疫霉病', desc: '预测霜疫霉病发生风险', showCity: true },
  { value: 'tanjubing', label: '炭疽病', desc: '预测炭疽病发生风险', showCity: false },
  { value: 'yield', label: '产量预测', desc: '预测荔枝产量', showCity: false },
]

const selectedType = ref('chunxiang')
const cityCode = ref('441284')
const loading = ref(false)
const result = ref(null)
const activeCollapse = ref([])

const showCityCode = computed(() => {
  const item = predictTypes.find((i) => i.value === selectedType.value)
  return item?.showCity
})

const currentTypeLabel = computed(() => {
  const item = predictTypes.find((i) => i.value === selectedType.value)
  return item?.label || '预测'
})

const riskLevel = computed(() => {
  if (!result.value) return ''
  // 兼容不同API返回的风险等级字段名
  return result.value.orchard_risk_level
    || result.value.risk_level
    || result.value.level
    || result.value.risk
    || ''
})

const riskClass = computed(() => {
  const level = riskLevel.value
  if (level.includes('高') || level === 'high') return 'border-red-200 bg-red-50 text-red-700'
  if (level.includes('中') || level === 'medium') return 'border-amber-200 bg-amber-50 text-amber-700'
  return 'border-green-200 bg-green-50 text-green-700'
})

const metrics = computed(() => {
  if (!result.value) return []
  const d = result.value
  const list = []

  const add = (key, label, formatter) => {
    if (d[key] !== undefined && d[key] !== null && key !== 'risk_level' && key !== 'risk' && key !== 'orchard_risk_level') {
      list.push({ label, value: formatter ? formatter(d[key]) : d[key] })
    }
  }

  add('probability', '发生概率')
  add('temperature', '温度')
  add('humidity', '湿度')
  add('rainfall', '降雨量')
  add('forecast', '预测结果')
  add('yield', '预计产量')
  add('score', '风险分数')
  add('orchard_survival_prob', '果园生存概率', v => typeof v === 'number' ? (v * 100).toFixed(1) + '%' : v)
  add('weather_source', '天气来源')
  add('nums', '预测数量')
  add('predicted_yield_kTons', '预测产量(万吨)')

  return list.slice(0, 6)
})

const advice = computed(() => {
  if (!result.value) return ''
  const type = selectedType.value
  if (type === 'shuangyimeibing') return '高温高湿天气利于霜疫霉病发生，注意果园通风透光，必要时提前喷药保护。'
  if (type === 'chunxiang') return '椿象危害嫩梢、花穗和果实。成虫出土期及时喷药，减少越冬虫源。'
  if (type === 'tanjubing') return '炭疽病多雨季节易发生，注意清园、增强树势，发病初期及时防治。'
  if (type === 'yield') return '产量预测需结合历史数据、气象和管理水平综合判断，建议以实际采收为准。'
  return ''
})

async function submitPredict() {
  loading.value = true
  result.value = null

  try {
    const payload = { api_type: selectedType.value }
    if (showCityCode.value) payload.city_code = cityCode.value
    const { data } = await predictRisk(payload)
    result.value = data
  } catch (error) {
    ElMessage.error('预测请求失败，请稍后重试')
  } finally {
    loading.value = false
  }
}
</script>
