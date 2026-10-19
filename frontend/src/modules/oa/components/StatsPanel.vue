<script setup lang="ts">
/** OA 统计面板（看板/管理统计共用）：卡片 + 图表；默认插槽放追加内容（如积压表）。 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { OaStats } from '@/api/types'

defineOptions({ name: 'OaStatsPanel' })

const props = defineProps<{ stats: OaStats | null }>()

echarts.use([BarChart, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const { t } = useI18n()

const byFormEl = ref<HTMLElement | null>(null)
const byStatusEl = ref<HTMLElement | null>(null)
const trendEl = ref<HTMLElement | null>(null)
const charts: echarts.ECharts[] = []
let resizeObserver: ResizeObserver | null = null

const STATUS_ORDER = ['running', 'approved', 'rejected', 'withdrawn', 'terminated']

function statusLabel(s: string) {
  const key = `oa.status.${s}`
  const tr = t(key)
  return tr === key ? s : tr
}

const passRate = computed(() => {
  const s = props.stats
  if (!s) return '-'
  const approved = s.byStatus.approved ?? 0
  const rejected = s.byStatus.rejected ?? 0
  return approved + rejected > 0 ? `${Math.round((approved / (approved + rejected)) * 100)}%` : '-'
})

function renderCharts() {
  const s = props.stats
  if (!s) return
  charts.forEach((c) => c.dispose())
  charts.length = 0

  if (byFormEl.value) {
    const c = echarts.init(byFormEl.value)
    c.setOption({
      tooltip: { trigger: 'item' },
      legend: { bottom: 0 },
      series: [
        {
          type: 'pie',
          radius: ['40%', '68%'],
          center: ['50%', '44%'],
          data: s.byForm.map((f) => ({ name: f.formName, value: f.count })),
        },
      ],
    })
    charts.push(c)
  }
  if (byStatusEl.value) {
    const c = echarts.init(byStatusEl.value)
    c.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 16, top: 24, bottom: 28 },
      xAxis: { type: 'category', data: STATUS_ORDER.filter((k) => s.byStatus[k]).map(statusLabel) },
      yAxis: { type: 'value', minInterval: 1 },
      series: [
        {
          type: 'bar',
          barWidth: 36,
          itemStyle: { color: '#409eff', borderRadius: [4, 4, 0, 0] },
          data: STATUS_ORDER.filter((k) => s.byStatus[k]).map((k) => s.byStatus[k]),
        },
      ],
    })
    charts.push(c)
  }
  if (trendEl.value) {
    const c = echarts.init(trendEl.value)
    c.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 16, top: 24, bottom: 28 },
      xAxis: { type: 'category', data: s.trend.map((p) => p.month) },
      yAxis: { type: 'value', minInterval: 1 },
      series: [
        {
          type: 'line',
          smooth: true,
          areaStyle: { opacity: 0.15 },
          itemStyle: { color: '#409eff' },
          data: s.trend.map((p) => p.count),
        },
      ],
    })
    charts.push(c)
  }
}

watch(
  () => props.stats,
  () => requestAnimationFrame(renderCharts),
)

onMounted(() => {
  renderCharts()
  resizeObserver = new ResizeObserver(() => charts.forEach((c) => c.resize()))
  ;[byFormEl.value, byStatusEl.value, trendEl.value].forEach((el) => el && resizeObserver?.observe(el))
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  charts.forEach((c) => c.dispose())
})
</script>

<template>
  <div v-if="stats" class="stats-body">
    <div class="stat-cards">
      <div class="stat-card">
        <div class="stat-label">{{ t('oa.stats.total') }}</div>
        <div class="stat-value">{{ stats.total }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('oa.stats.inFlight') }}</div>
        <div class="stat-value">{{ stats.inFlight }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('oa.stats.approvedRate') }}</div>
        <div class="stat-value">{{ passRate }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('oa.stats.avgDuration') }}</div>
        <div class="stat-value">{{ stats.avgDurationHours }}<span class="stat-unit">{{ t('oa.stats.hours') }}</span></div>
      </div>
    </div>

    <div class="chart-grid">
      <div class="chart-card">
        <div class="chart-title">{{ t('oa.stats.byForm') }}</div>
        <div ref="byFormEl" class="chart-box" />
      </div>
      <div class="chart-card">
        <div class="chart-title">{{ t('oa.stats.byStatus') }}</div>
        <div ref="byStatusEl" class="chart-box" />
      </div>
      <div class="chart-card chart-wide">
        <div class="chart-title">{{ t('oa.stats.trend') }}</div>
        <div ref="trendEl" class="chart-box" />
      </div>
    </div>

    <slot />
  </div>
</template>

<style scoped>
.stats-body {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.stat-cards {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--bs-space-3);
}

.stat-card {
  background: var(--bs-color-bg-surface);
  border-radius: var(--bs-radius-md);
  box-shadow: var(--bs-shadow-elevation1);
  padding: var(--bs-space-3);
}

.stat-label {
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-xs, 12px);
}

.stat-value {
  margin-top: var(--bs-space-2);
  font-size: 26px;
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.stat-unit {
  margin-left: var(--bs-space-1);
  font-size: var(--bs-typography-font-size-xs, 12px);
  font-weight: 400;
  color: var(--bs-color-fg-muted);
}

.chart-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--bs-space-3);
}

.chart-card {
  background: var(--bs-color-bg-surface);
  border-radius: var(--bs-radius-md);
  box-shadow: var(--bs-shadow-elevation1);
  padding: var(--bs-space-3);
}

.chart-wide {
  grid-column: 1 / -1;
}

.chart-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
  margin-bottom: var(--bs-space-2);
}

.chart-box {
  height: 260px;
}
</style>
