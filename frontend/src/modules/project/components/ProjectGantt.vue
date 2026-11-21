<script setup lang="ts">
/**
 * 项目甘特（B5）：项目任务（甘特行）按起止日期绘制，进度以条内高亮段表达；
 * 里程碑渲染为菱形。颜色取自 --bs-* 语义令牌（canvas 不识别 var()，经 statusColor 解析）。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import * as echarts from 'echarts/core'
import { CustomChart } from 'echarts/charts'
import { DataZoomComponent, GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { ProjectTask } from '@/api/types'
import { statusColor, resolveToken, watchChartTheme } from '@/utils/chartTheme'

echarts.use([CustomChart, GridComponent, TooltipComponent, DataZoomComponent, CanvasRenderer])

defineOptions({ name: 'ProjectGantt' })

const props = defineProps<{
  items: ProjectTask[]
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'open', item: ProjectTask): void
}>()

const { t } = useI18n()

const DAY = 24 * 3600 * 1000

const STATUS_KEYS: { value: string; labelKey: string }[] = [
  { value: 'pending', labelKey: 'project.status.pending' },
  { value: 'doing', labelKey: 'project.status.doing' },
  { value: 'done', labelKey: 'project.status.done' },
  { value: 'delayed', labelKey: 'project.status.delayed' },
]

const statusColors = ref<Record<string, string>>({})

function refreshColors() {
  const m: Record<string, string> = {}
  for (const s of STATUS_KEYS) m[s.value] = statusColor(s.value)
  statusColors.value = m
}

interface GanttRow {
  item: ProjectTask
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
  for (const it of props.items) {
    const start = parseTime(it.startDate)
    if (Number.isNaN(start)) continue
    let end = parseTime(it.endDate)
    if (Number.isNaN(end) || end < start) end = start + DAY
    list.push({ item: it, start, end, label: it.taskName || it.taskNo || '-' })
  }
  return list.sort((a, b) => a.start - b.start)
})

const noDateCount = computed(() => props.items.length - rows.value.length)

const legendStatuses = computed(() => {
  const present = new Set<string>(rows.value.map((r) => r.item.status))
  return STATUS_KEYS.filter((s) => present.has(s.value))
})

const chartEl = ref<HTMLDivElement>()
let chart: echarts.ECharts | null = null
let resizeObserver: ResizeObserver | null = null

/**
 * 里程碑渲染为菱形，普通任务渲染为「底条 + 进度段」双矩形。
 * 进度段宽度按 start→end 的时间比例计算。
 */
function renderItem(_params: any, api: any) {
  const idx = api.value(0)
  const start = api.coord([api.value(1), idx])
  const end = api.coord([api.value(2), idx])
  const size = api.size([0, 1]) as number[]
  const height = Math.min((size[1] ?? 24) * 0.6, 18)
  const progress = Math.max(0, Math.min(100, Number(api.value(3)) || 0))
  const milestone = Boolean(api.value(4))
  const color = statusColors.value[String(api.value(5))] ?? statusColor('')

  if (milestone) {
    const r = height / 2
    const cx = ((start[0] ?? 0) + (end[0] ?? 0)) / 2
    const cy = (start[1] ?? 0) - r
    return {
      type: 'polygon',
      shape: { points: [[cx, cy - r], [cx + r, cy], [cx, cy + r], [cx - r, cy]] },
      style: { fill: color },
    }
  }

  const width = Math.max((end[0] ?? 0) - (start[0] ?? 0), 3)
  const children: any[] = [
    {
      type: 'rect',
      shape: {
        x: start[0] ?? 0,
        y: (start[1] ?? 0) - height / 2,
        width,
        height,
        r: 3,
      },
      style: { fill: resolveToken('--bs-color-fill-light', '#ebeef5') },
    },
  ]
  if (progress > 0) {
    children.push({
      type: 'rect',
      shape: {
        x: start[0] ?? 0,
        y: (start[1] ?? 0) - height / 2,
        width: Math.max((width * progress) / 100, 2),
        height,
        r: 3,
      },
      style: { fill: color },
    })
  }
  return { type: 'group', children }
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
        const statusKey = STATUS_KEYS.find((s) => s.value === r.item.status)
        const statusLabel = statusKey ? t(statusKey.labelKey) : r.item.status
        return [
          `<b>${r.item.taskNo || '-'}</b> ${r.item.taskName || ''}`,
          `${t('project.status.pending')}: ${statusLabel}`,
          `${t('project.groupCode')}: ${r.item.groupText || r.item.groupCode || '-'}`,
          `${t('project.ownerName')}: ${r.item.ownerName || '-'}`,
          `${t('project.startDate')}: ${fmtDate(r.start)}`,
          `${t('project.endDate')}: ${fmtDate(r.end)}`,
          `${t('project.progress')}: ${r.item.progress || 0}%`,
        ].join('<br/>')
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
        width: 140,
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
        data: data.map((r, i) => ({
          value: [
            i,
            r.start,
            r.end,
            r.item.progress || 0,
            r.item.milestone,
            r.item.status,
          ],
        })),
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
    if (r) emit('open', r.item)
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
  <div class="project-gantt" v-loading="props.loading">
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
    <el-empty v-else-if="!props.loading" :description="t('project.ganttEmpty')" />
  </div>
</template>

<style scoped>
.project-gantt {
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
