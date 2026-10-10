<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import * as echarts from 'echarts/core'
import { CustomChart } from 'echarts/charts'
import { DataZoomComponent, GridComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import type { Task, TaskStatus } from '@/api/types'

echarts.use([CustomChart, GridComponent, TooltipComponent, DataZoomComponent, CanvasRenderer])

defineOptions({ name: 'TaskGantt' })

const props = defineProps<{
  tasks: Task[]
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'open', task: Task): void
}>()

const { t } = useI18n()

interface GanttRow {
  task: Task
  start: number
  end: number
}

const DAY = 24 * 3600 * 1000
const TERMINAL: TaskStatus[] = ['finished', 'closed', 'stopped']

const STATUS_COLORS: Record<string, string> = {
  draft: '#909399',
  assigning: '#e6a23c',
  assigned: '#409eff',
  in_progress: '#626aef',
  finished: '#67c23a',
  closed: '#303133',
  stopped: '#f56c6c',
  settled: '#13c2c2',
}

const STATUS_KEYS: { value: string; labelKey: string }[] = [
  { value: 'draft', labelKey: 'task.task.statusDraft' },
  { value: 'assigning', labelKey: 'task.task.statusAssigning' },
  { value: 'assigned', labelKey: 'task.task.statusAssigned' },
  { value: 'in_progress', labelKey: 'task.task.statusInProgress' },
  { value: 'finished', labelKey: 'task.task.statusFinished' },
  { value: 'closed', labelKey: 'task.task.statusClosed' },
  { value: 'stopped', labelKey: 'task.task.statusStopped' },
]

function parseTime(v: string | undefined | null): number {
  if (!v) return NaN
  const ts = new Date(v.replace(' ', 'T')).getTime()
  return Number.isNaN(ts) ? NaN : ts
}

// 后端无单独完成时间字段：结束点取 计划完成日期 → 终态任务的更新时间 → 当前时间
function endOf(task: Task, start: number): number {
  let end = parseTime(task.planFinishDate)
  if (Number.isNaN(end)) {
    end = TERMINAL.includes(task.status) ? parseTime(task.updateTime) : Date.now()
  }
  if (Number.isNaN(end) || end < start) end = start + DAY
  return end
}

const rows = computed<GanttRow[]>(() => {
  const list: GanttRow[] = []
  for (const task of props.tasks) {
    const start = parseTime(task.createTime)
    if (Number.isNaN(start)) continue
    list.push({ task, start, end: endOf(task, start) })
  }
  return list.sort((a, b) => a.start - b.start)
})

const legendStatuses = computed(() => {
  const present = new Set(rows.value.map((r) => r.task.status))
  return STATUS_KEYS.filter((s) => present.has(s.value as TaskStatus))
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
    style: { fill: STATUS_COLORS[String(api.value(3))] ?? '#909399' },
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
        const row = data[p.dataIndex]
        if (!row) return ''
        const statusKey = STATUS_KEYS.find((s) => s.value === row.task.status)
        const statusLabel = statusKey ? t(statusKey.labelKey) : row.task.status
        return [
          `<b>${row.task.taskNo}</b> ${row.task.taskName}`,
          `${t('task.task.status')}: ${statusLabel}`,
          `${t('task.task.createTime')}: ${fmtDate(row.start)}`,
          `${t('task.task.ganttEnd')}: ${fmtDate(row.end)}`,
        ].join('<br/>')
      },
    },
    grid: { left: 8, right: 36, top: 8, bottom: 8, containLabel: true },
    xAxis: { type: 'time', axisLabel: { hideOverlap: true } },
    yAxis: {
      type: 'category',
      inverse: true,
      data: data.map((r) => r.task.taskNo),
      axisLabel: { width: 110, overflow: 'truncate' },
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
        data: data.map((r, i) => ({ value: [i, r.start, r.end, r.task.status] })),
      },
    ],
  }
}

function render() {
  if (!chart) return
  chart.setOption(buildOption(), { notMerge: true })
}

onMounted(() => {
  if (!chartEl.value) return
  chart = echarts.init(chartEl.value)
  chart.on('click', (p: any) => {
    const row = rows.value[p.dataIndex]
    if (row) emit('open', row.task)
  })
  resizeObserver = new ResizeObserver(() => chart?.resize())
  resizeObserver.observe(chartEl.value)
  render()
})

watch(rows, () => render())

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  chart?.dispose()
  chart = null
})
</script>

<template>
  <div class="task-gantt" v-loading="props.loading">
    <div v-if="legendStatuses.length" class="gantt-legend">
      <span v-for="s in legendStatuses" :key="s.value" class="legend-item">
        <i class="legend-dot" :style="{ background: STATUS_COLORS[s.value] }" />
        {{ t(s.labelKey) }}
      </span>
    </div>
    <div v-if="rows.length" ref="chartEl" class="gantt-chart" />
    <el-empty v-else-if="!props.loading" :description="t('task.task.ganttEmpty')" />
  </div>
</template>

<style scoped>
.task-gantt {
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

.gantt-chart {
  flex: 1;
  min-height: 0;
}
</style>
