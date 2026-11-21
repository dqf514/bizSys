<script setup lang="ts">
/**
 * 排程甘特（B5）：按「资源 / 任务」一行一条排程时段绘制。
 * 颜色取自 --bs-* 语义令牌（canvas 不识别 var()，经 statusColor 解析为字面值）。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import * as echarts from 'echarts/core'
import { CustomChart } from 'echarts/charts'
import { DataZoomComponent, GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ProdSchedule } from '@/api/types'
import { statusColor, resolveToken, watchChartTheme } from '@/utils/chartTheme'

echarts.use([CustomChart, GridComponent, TooltipComponent, DataZoomComponent, CanvasRenderer])

defineOptions({ name: 'ScheduleGantt' })

const props = defineProps<{
  schedules: ProdSchedule[]
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'open', schedule: ProdSchedule): void
}>()

const { t } = useI18n()

const DAY = 24 * 3600 * 1000

const STATUS_KEYS: { value: string; labelKey: string }[] = [
  { value: 'scheduled', labelKey: 'production.status.scheduled' },
  { value: 'published', labelKey: 'production.status.published' },
  { value: 'confirmed', labelKey: 'production.status.confirmed' },
  { value: 'done', labelKey: 'production.status.done' },
  { value: 'conflict', labelKey: 'production.status.conflict' },
  { value: 'cancelled', labelKey: 'production.status.cancelled' },
]

const statusColors = ref<Record<string, string>>({})

function refreshColors() {
  const m: Record<string, string> = {}
  for (const s of STATUS_KEYS) m[s.value] = statusColor(s.value)
  statusColors.value = m
}

interface GanttRow {
  row: ProdSchedule
  start: number
  end: number
  label: string
}

function parseTime(v: string | undefined | null): number {
  if (!v) return NaN
  const ts = new Date(v.replace(' ', 'T')).getTime()
  return Number.isNaN(ts) ? NaN : ts
}

const rows = computed<GanttRow[]>(() => {
  const list: GanttRow[] = []
  for (const s of props.schedules) {
    const start = parseTime(s.planStart)
    if (Number.isNaN(start)) continue
    let end = parseTime(s.planEnd)
    if (Number.isNaN(end) || end <= start) end = start + DAY
    const resource = s.resourceName || s.resourceCode || s.resourceTypeText || '-'
    list.push({ row: s, start, end, label: `${resource} · ${s.taskNo || s.scheduleNo}` })
  }
  return list.sort((a, b) => a.start - b.start)
})

const noDateCount = computed(() => props.schedules.length - rows.value.length)

const legendStatuses = computed(() => {
  const present = new Set<string>(rows.value.map((r) => r.row.status))
  return STATUS_KEYS.filter((s) => present.has(s.value))
})

const chartEl = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

function renderItem(_params: any, api: any) {
  const idx = api.value(0)
  const start = api.coord([api.value(1), idx])
  const end = api.coord([api.value(2), idx])
  const size = api.size([0, 1]) as number[]
  const height = Math.min((size[1] ?? 24) * 0.6, 18)
  return {
    type: 'rect',
    shape: {
      x: start[0] ?? 0,
      y: (start[1] ?? 0) - height / 2,
      width: Math.max((end[0] ?? 0) - (start[0] ?? 0), 3),
      height,
      r: 3,
    },
    style: { fill: statusColors.value[String(api.value(3))] ?? statusColor('') },
  }
}

function fmtDate(ts: number): string {
  const d = new Date(ts)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}

function buildOption() {
  const data = rows.value
  return {
    animation: false,
    tooltip: {
      trigger: 'item',
      formatter: (p: any) => {
        const r = data[p.dataIndex]
        if (!r) return ''
        const statusKey = STATUS_KEYS.find((s) => s.value === r.row.status)
        const statusLabel = statusKey ? t(statusKey.labelKey) : r.row.status
        return [
          `<b>${r.row.scheduleNo}</b> ${r.row.taskName || r.row.taskNo || ''}`,
          `${t('production.schedule.resourceType')}: ${r.row.resourceTypeText || r.row.resourceType}`,
          `${t('production.schedule.resourceName')}: ${r.row.resourceName || '-'}`,
          `${t('production.status.scheduled')}: ${statusLabel}`,
          `${t('production.schedule.planStart')}: ${fmtDate(r.start)}`,
          `${t('production.schedule.planEnd')}: ${fmtDate(r.end)}`,
          r.row.conflictReason ? `${t('production.schedule.conflictReason')}: ${r.row.conflictReason}` : '',
        ]
          .filter(Boolean)
          .join('<br/>')
      },
    },
    grid: { left: 8, right: 36, top: 8, bottom: 8, containLabel: true },
    xAxis: {
      type: 'time',
      axisLabel: { hideOverlap: true, color: resolveToken('--bs-color-fg-muted', '#909399') },
      axisLine: { lineStyle: { color: resolveToken('--bs-color-border-default', '#dcdfe6') } },
    },
    yAxis: {
      type: 'category',
      inverse: true,
      data: data.map((r) => r.label),
      axisLabel: {
        width: 160,
        overflow: 'truncate',
        color: resolveToken('--bs-color-fg-secondary', '#5a6472'),
      },
      axisLine: { lineStyle: { color: resolveToken('--bs-color-border-default', '#dcdfe6') } },
    },
    dataZoom: [
      { type: 'inside', yAxisIndex: 0, filterMode: 'none', zoomOnMouseWheel: false, moveOnMouseWheel: true },
      { type: 'slider', yAxisIndex: 0, filterMode: 'none', width: 14, right: 6, top: 8, bottom: 8 },
    ],
    series: [
      {
        type: 'custom',
        renderItem,
        encode: { x: [1, 2], y: 0 },
        data: data.map((r, i) => ({ value: [i, r.start, r.end, r.row.status] })),
      },
    ],
  }
}

function render() {
  if (!chart) return
  chart.setOption(buildOption(), { notMerge: true })
}

function mountChart(el: HTMLDivElement) {
  if (chart) return
  chart = echarts.init(el)
  chart.on('click', (p: any) => {
    const r = rows.value[p.dataIndex]
    if (r) emit('open', r.row)
  })
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(el)
  render()
}

function unmountChart() {
  resizeObserver?.disconnect()
  resizeObserver = null
  chart?.dispose()
  chart = null
}

onMounted(() => {
  refreshColors()
  if (chartEl.value) mountChart(chartEl.value)
})

watchChartTheme(() => {
  refreshColors()
  render()
})

watch(
  chartEl,
  (el, prev) => {
    if (prev) unmountChart()
    if (el) mountChart(el)
  },
  { flush: 'post' },
)

watch(rows, () => render())

onBeforeUnmount(() => unmountChart())
</script>

<template>
  <div class="schedule-gantt" v-loading="props.loading">
    <div v-if="legendStatuses.length || noDateCount > 0" class="gantt-legend">
      <span v-for="s in legendStatuses" :key="s.value" class="legend-item">
        <i class="legend-dot" :style="{ background: statusColors[s.value] }" />
        {{ t(s.labelKey) }}
      </span>
      <span v-if="noDateCount > 0" class="gantt-hint">
        {{ t('task.task.ganttNoDate', { count: noDateCount }) }}
      </span>
    </div>
    <div v-if="rows.length" ref="chartEl" class="gantt-chart" />
    <el-empty v-else-if="!props.loading" :description="t('production.schedule.empty')" />
  </div>
</template>

<style scoped>
.schedule-gantt {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--bs-color-bg-surface);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  overflow: hidden;
}

.gantt-legend {
  display: flex;
  align-items: center;
  gap: var(--bs-space-3);
  flex-wrap: wrap;
  padding: var(--bs-space-2) var(--bs-space-3);
  border-bottom: 1px solid var(--bs-color-border-subtle);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: var(--bs-space-1);
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
}

.gantt-hint {
  margin-left: auto;
}

.gantt-chart {
  flex: 1;
  min-height: 0;
}
</style>
