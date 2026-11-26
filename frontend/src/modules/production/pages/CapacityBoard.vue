<script setup lang="ts">
/**
 * 产能利用率看板（B7 CSV 4）。
 *
 * 风洞台次利用率 / 风洞中心设备利用率 / 加工中心设备利用率，与设备台账联动。
 * 口径（后端 capacity_router.py 与本页面共用）：
 *   利用率 = 排程占用工时 ÷ 可用工时 × 100%
 *   可用工时 = 期间天数 × 24 小时 × 设备可用系数（维护/故障 50%，报废不计）
 *   冲突排程单独计数，不占用工时；利用率可以 > 100%（超负荷）
 */
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import {
  getCapacityBoard,
  getCapacityEquipment,
  type CapacityBoard,
  type CapacityEquipment,
  type CapacityEquipmentDetail,
} from '@/api/production'
import { chartPalette, resolveToken, watchChartTheme } from '@/utils/chartTheme'

defineOptions({ name: 'CapacityBoard' })

echarts.use([BarChart, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const { t } = useI18n()

/* ---------------- 筛选条件 ---------------- */

function fmtDate(d: Date) {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

const today = new Date()
const defaultFrom = new Date(today)
defaultFrom.setDate(defaultFrom.getDate() - 29)

const filters = reactive({
  range: [fmtDate(defaultFrom), fmtDate(today)] as string[],
  workshop: '' as string,
  category: '' as string,
})

const CATEGORY_KEYS = ['wind_tunnel', 'cfd', 'machining', 'test', 'other']

const workshopOptions = ref<{ label: string; value: string }[]>([])
const categoryOptions = computed(() => [
  { label: t('production.capacity.all'), value: '' },
  ...CATEGORY_KEYS.map((k) => ({ label: categoryText(k), value: k })),
])

function categoryText(c: string) {
  const key = `production.capacity.categories.${c}`
  const v = t(key)
  return v === key ? c || '-' : v
}

function statusTextOf(s: string) {
  const key = `production.capacity.statuses.${s}`
  const v = t(key)
  return v === key ? s || '-' : v
}

function workshopText(w: string) {
  return w || t('production.capacity.unassigned')
}

/* ---------------- 数据加载 ---------------- */

const board = ref<CapacityBoard | null>(null)
const loading = ref(false)

function currentParams() {
  const [from, to] = filters.range || []
  return {
    from: from || undefined,
    to: to || undefined,
    workshop: filters.workshop || undefined,
    category: filters.category || undefined,
  }
}

async function loadOptions() {
  try {
    const data = await getCapacityBoard({})
    workshopOptions.value = (data.byWorkshop || []).map((w) => ({
      label: workshopText(w.workshop),
      value: w.workshop,
    }))
  } catch {
    workshopOptions.value = []
  }
}

async function load() {
  loading.value = true
  try {
    board.value = await getCapacityBoard(currentParams())
  } catch {
    board.value = null
  } finally {
    loading.value = false
    await nextTick()
    renderCharts()
  }
}

function onRefresh() {
  void load()
}

function resetFilters() {
  filters.range = [fmtDate(defaultFrom), fmtDate(today)]
  filters.workshop = ''
  filters.category = ''
  void load()
}

watch(() => [filters.range.join(','), filters.workshop, filters.category], () => void load())

onMounted(() => {
  void loadOptions()
  void load()
})

/* ---------------- 图表 ---------------- */

const categoryEl = ref<HTMLElement | null>(null)
const trendEl = ref<HTMLElement | null>(null)
const workshopEl = ref<HTMLElement | null>(null)
const charts: echarts.ECharts[] = []
let resizeObserver: ResizeObserver | null = null

function renderCharts() {
  const b = board.value
  charts.forEach((c) => c.dispose())
  charts.length = 0
  if (!b) return

  const palette = chartPalette()
  const primary = palette[0]
  const success = palette[2]
  const warning = palette[3]
  const axisText = resolveToken('--bs-color-fg-muted', '#909399')
  const axis = {
    axisLabel: { color: axisText },
    axisLine: { lineStyle: { color: resolveToken('--bs-color-border-default', '#dcdfe6') } },
    splitLine: { lineStyle: { color: resolveToken('--bs-color-border-subtle', '#e4e7ed') } },
  }

  // 1. 分类利用率：柱状（利用率 % + 设备数）
  if (categoryEl.value) {
    const c = echarts.init(categoryEl.value)
    c.setOption({
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0, textStyle: { color: axisText } },
      grid: { left: 48, right: 48, top: 24, bottom: 48 },
      xAxis: {
        type: 'category',
        data: (b.byCategory || []).map((r) => categoryText(r.category)),
        ...axis,
      },
      yAxis: [
        { type: 'value', name: '%', ...axis },
        { type: 'value', minInterval: 1, ...axis },
      ],
      series: [
        {
          name: t('production.capacity.utilization'),
          type: 'bar',
          barWidth: 28,
          itemStyle: { color: primary, borderRadius: [4, 4, 0, 0] },
          data: (b.byCategory || []).map((r) => r.utilization),
        },
        {
          name: t('production.capacity.equipmentCount'),
          type: 'bar',
          barWidth: 28,
          yAxisIndex: 1,
          itemStyle: { color: success, opacity: 0.55, borderRadius: [4, 4, 0, 0] },
          data: (b.byCategory || []).map((r) => r.equipmentCount),
        },
      ],
    })
    charts.push(c)
  }

  // 2. 趋势：利用率折线 + 排程工时柱状（双轴）
  if (trendEl.value) {
    const c = echarts.init(trendEl.value)
    c.setOption({
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0, textStyle: { color: axisText } },
      grid: { left: 48, right: 48, top: 24, bottom: 48 },
      xAxis: {
        type: 'category',
        data: (b.trend || []).map((p) => p.bucket),
        ...axis,
      },
      yAxis: [
        { type: 'value', name: '%', ...axis },
        { type: 'value', ...axis },
      ],
      series: [
        {
          name: t('production.capacity.utilization'),
          type: 'line',
          smooth: true,
          areaStyle: { opacity: 0.15 },
          itemStyle: { color: primary },
          data: (b.trend || []).map((p) => p.utilization),
        },
        {
          name: t('production.capacity.scheduleHours'),
          type: 'bar',
          barWidth: 16,
          yAxisIndex: 1,
          itemStyle: { color: warning, opacity: 0.5 },
          data: (b.trend || []).map((p) => p.scheduleHours),
        },
      ],
    })
    charts.push(c)
  }

  // 3. 车间利用率：环形图（按排程工时占比）
  if (workshopEl.value) {
    const c = echarts.init(workshopEl.value)
    c.setOption({
      tooltip: { trigger: 'item' },
      legend: { bottom: 0, type: 'scroll', textStyle: { color: axisText } },
      series: [
        {
          name: t('production.capacity.scheduleHours'),
          type: 'pie',
          radius: ['42%', '68%'],
          center: ['50%', '44%'],
          avoidLabelOverlap: true,
          itemStyle: { borderRadius: 4, borderColor: resolveToken('--bs-color-bg-surface', '#ffffff') },
          label: { color: axisText },
          data: (b.byWorkshop || []).map((r, i) => ({
            name: workshopText(r.workshop),
            value: r.scheduleHours,
            itemStyle: { color: palette[i % palette.length] },
          })),
        },
      ],
    })
    charts.push(c)
  }
}

watchChartTheme(() => renderCharts())

onMounted(() => {
  resizeObserver = new ResizeObserver(() => charts.forEach((c) => c.resize()))
  ;[categoryEl.value, trendEl.value, workshopEl.value].forEach((el) => el && resizeObserver?.observe(el))
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  charts.forEach((c) => c.dispose())
  charts.length = 0
})

/* ---------------- 设备明细 ---------------- */

const columns: ListColumn[] = [
  { prop: 'equipmentNo', labelKey: 'production.capacity.equipmentNo', width: 130 },
  { prop: 'equipmentName', labelKey: 'production.capacity.equipmentName', minWidth: 150 },
  { prop: 'category', labelKey: 'production.capacity.category', width: 100, slot: 'category' },
  { prop: 'workshop', labelKey: 'production.capacity.workshop', width: 120, slot: 'workshop' },
  { prop: 'status', labelKey: 'production.capacity.status', width: 100, slot: 'status' },
  { prop: 'scheduleHours', labelKey: 'production.capacity.scheduleHours', width: 110, align: 'right' },
  { prop: 'availableHours', labelKey: 'production.capacity.availableHours', width: 110, align: 'right' },
  { prop: 'utilization', labelKey: 'production.capacity.utilization', width: 160, slot: 'utilization' },
  { prop: 'scheduleCount', labelKey: 'production.capacity.scheduleCount', width: 100, align: 'right' },
  { prop: 'conflictCount', labelKey: 'production.capacity.conflictCountCol', width: 90, align: 'right' },
]

const equipmentRows = computed(() => (board.value?.equipment ?? []) as unknown as Record<string, unknown>[])

function utilWidth(row: Record<string, unknown>) {
  const u = Number(row.utilization) || 0
  return `${Math.min(Math.max(u, 0), 100)}%`
}

function num(v: unknown, digits = 1) {
  const n = Number(v) || 0
  return n.toFixed(digits)
}

/* ---------------- 设备下钻抽屉 ---------------- */

const detail = reactive({
  visible: false,
  loading: false,
  data: null as CapacityEquipmentDetail | null,
})

async function openDetail(row: Record<string, unknown>) {
  const eq = row as unknown as CapacityEquipment
  if (eq.equipmentId == null) return
  detail.visible = true
  detail.loading = true
  detail.data = null
  try {
    const [from, to] = filters.range || []
    detail.data = await getCapacityEquipment(eq.equipmentId, { from: from || undefined, to: to || undefined })
  } catch {
    detail.data = null
  } finally {
    detail.loading = false
  }
}

function onRowClick(row: Record<string, unknown>) {
  void openDetail(row)
}
</script>

<template>
  <div class="bs-page bs-page--scroll capacity-page">
    <!-- 筛选条 -->
    <div class="filter-bar">
      <el-date-picker
        v-model="filters.range"
        type="daterange"
        value-format="YYYY-MM-DD"
        range-separator="~"
        :clearable="false"
        style="width: 260px"
      />
      <el-select v-model="filters.workshop" clearable style="width: 180px">
        <el-option
          v-for="opt in workshopOptions"
          :key="opt.value || 'none'"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
      <el-select v-model="filters.category" clearable style="width: 160px">
        <el-option
          v-for="opt in categoryOptions"
          :key="opt.value || 'none'"
          :label="opt.label"
          :value="opt.value"
        />
      </el-select>
      <el-button type="primary" @click="onRefresh">{{ t('common.action.refresh') }}</el-button>
      <el-button @click="resetFilters">{{ t('common.action.reset') }}</el-button>
    </div>

    <!-- 口径说明 -->
    <el-alert
      class="caliber-alert"
      type="info"
      :closable="false"
      :title="t('production.capacity.caliberTip')"
    />

    <!-- 统计卡片 -->
    <div class="stat-cards" v-loading="loading">
      <div class="stat-card">
        <div class="stat-label">{{ t('production.capacity.equipmentTotal') }}</div>
        <div class="stat-value">{{ board?.summary.equipmentTotal ?? 0 }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('production.capacity.scheduledEquipment') }}</div>
        <div class="stat-value">{{ board?.summary.scheduledEquipment ?? 0 }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('production.capacity.avgUtilization') }}</div>
        <div class="stat-value">
          {{ num(board?.summary.avgUtilization) }}<span class="stat-unit">%</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('production.capacity.totalScheduleHours') }}</div>
        <div class="stat-value">
          {{ num(board?.summary.totalScheduleHours) }}<span class="stat-unit">{{ t('production.capacity.unitHour') }}</span>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('production.capacity.conflictCount') }}</div>
        <div class="stat-value" :class="{ danger: (board?.summary.conflictCount ?? 0) > 0 }">
          {{ board?.summary.conflictCount ?? 0 }}
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('production.capacity.overloadEquipment') }}</div>
        <div class="stat-value" :class="{ warning: (board?.summary.overloadEquipment ?? 0) > 0 }">
          {{ board?.summary.overloadEquipment ?? 0 }}
        </div>
      </div>
    </div>

    <!-- 图表区 -->
    <div class="chart-grid">
      <div class="chart-card">
        <el-tooltip :content="t('production.capacity.caliberTip')" placement="top">
          <div class="chart-title">{{ t('production.capacity.byCategoryTitle') }}</div>
        </el-tooltip>
        <div ref="categoryEl" class="chart-box" />
      </div>
      <div class="chart-card">
        <el-tooltip :content="t('production.capacity.caliberTip')" placement="top">
          <div class="chart-title">{{ t('production.capacity.trendTitle') }}</div>
        </el-tooltip>
        <div ref="trendEl" class="chart-box" />
      </div>
      <div class="chart-card">
        <el-tooltip :content="t('production.capacity.caliberTip')" placement="top">
          <div class="chart-title">{{ t('production.capacity.byWorkshopTitle') }}</div>
        </el-tooltip>
        <div ref="workshopEl" class="chart-box" />
      </div>
    </div>

    <!-- 设备明细 -->
    <div class="bs-page-card equipment-card">
      <div class="card-title">
        {{ t('production.capacity.equipmentTitle') }}
        <span v-if="board && board.summary.idleEquipment > 0" class="card-hint">
          {{ t('production.capacity.idleEquipment') }}: {{ board.summary.idleEquipment }}
        </span>
      </div>
      <el-alert
        v-if="board && board.summary.equipmentTotal === 0"
        class="card-alert"
        type="warning"
        :closable="false"
        :title="t('production.capacity.noEquipment')"
      />
      <ListTable
        :columns="columns"
        :data="equipmentRows"
        :loading="loading"
        :show-pagination="false"
        height="420"
        @row-click="onRowClick"
      >
        <template #category="{ row }">
          {{ categoryText(String(row.category || '')) }}
        </template>
        <template #workshop="{ row }">
          {{ workshopText(String(row.workshop || '')) }}
        </template>
        <template #status="{ row }">
          <el-tag size="small" effect="light" round>{{ statusTextOf(String(row.status || '')) }}</el-tag>
        </template>
        <template #utilization="{ row }">
          <div class="util-cell">
            <div class="util-track">
              <div
                class="util-fill"
                :class="{ 'is-over': Boolean(row.overloaded) }"
                :style="{ width: utilWidth(row) }"
              />
            </div>
            <span class="util-num" :class="{ 'is-over': Boolean(row.overloaded) }">
              {{ num(row.utilization) }}%
            </span>
          </div>
        </template>
      </ListTable>
    </div>

    <!-- 冲突清单 -->
    <div class="bs-page-card" v-if="(board?.conflicts ?? []).length">
      <div class="card-title">{{ t('production.capacity.conflictsTitle') }}</div>
      <ul class="conflict-list">
        <li v-for="(c, i) in board?.conflicts ?? []" :key="`${c.scheduleNo}-${i}`" class="conflict-item">
          <span class="c-no">{{ c.scheduleNo }}</span>
          <span class="c-equipment">{{ c.equipmentNo }} {{ c.equipmentName }}</span>
          <span class="c-task">{{ c.taskNo }} {{ c.taskName }}</span>
          <span class="c-time">{{ c.planStart }} → {{ c.planEnd }}</span>
          <span class="c-reason">{{ c.reason || '-' }}</span>
        </li>
      </ul>
    </div>

    <!-- 设备下钻抽屉 -->
    <el-drawer
      v-model="detail.visible"
      :title="t('production.capacity.detailTitle')"
      size="var(--bs-layout-drawer-lg)"
      append-to-body
    >
      <div v-loading="detail.loading" class="detail-body">
        <template v-if="detail.data">
          <el-descriptions :column="2" border size="small">
            <el-descriptions-item :label="t('production.capacity.equipmentNo')">
              {{ detail.data.equipment.equipmentNo || '-' }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('production.capacity.equipmentName')">
              {{ detail.data.equipment.equipmentName || '-' }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('production.capacity.category')">
              {{ categoryText(detail.data.equipment.category) }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('production.capacity.workshop')">
              {{ workshopText(detail.data.equipment.workshop) }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('production.capacity.status')">
              {{ statusTextOf(detail.data.equipment.status) }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('production.capacity.runHours')">
              {{ num(detail.data.equipment.runHours) }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('production.capacity.scheduleHours')">
              {{ num(detail.data.equipment.scheduleHours) }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('production.capacity.availableHours')">
              {{ num(detail.data.equipment.availableHours) }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('production.capacity.utilization')">
              {{ num(detail.data.equipment.utilization) }}%
            </el-descriptions-item>
            <el-descriptions-item :label="t('production.capacity.taskCount')">
              {{ detail.data.equipment.taskCount }}
            </el-descriptions-item>
            <el-descriptions-item :label="t('production.capacity.lastScheduleEnd')">
              {{ detail.data.equipment.lastScheduleEnd || '-' }}
            </el-descriptions-item>
          </el-descriptions>

          <div class="detail-section-title">{{ t('production.capacity.scheduleCount') }}</div>
          <el-table :data="detail.data.schedules" size="small" border stripe max-height="360">
            <el-table-column
              :label="t('production.capacity.scheduleNo')"
              prop="scheduleNo"
              width="150"
            />
            <el-table-column :label="t('production.capacity.taskNo')" prop="taskNo" width="130" />
            <el-table-column
              :label="t('production.capacity.taskName')"
              prop="taskName"
              min-width="140"
              show-overflow-tooltip
            />
            <el-table-column :label="t('production.capacity.planStart')" prop="planStart" width="150" />
            <el-table-column :label="t('production.capacity.planEnd')" prop="planEnd" width="150" />
            <el-table-column :label="t('production.capacity.duration')" prop="durationHours" width="100" />
            <el-table-column :label="t('production.capacity.status')" prop="statusText" width="100" />
          </el-table>
          <el-empty
            v-if="!detail.data.schedules.length"
            :description="t('production.capacity.noData')"
          />
        </template>
      </div>
    </el-drawer>
  </div>
</template>

<style scoped>
.capacity-page {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bs-space-2);
  align-items: center;
}

.caliber-alert {
  margin: 0;
}

.stat-cards {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: var(--bs-space-3);
}

.stat-card {
  background: var(--bs-color-bg-surface);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  padding: var(--bs-space-3);
}

.stat-label {
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-xs);
}

.stat-value {
  margin-top: var(--bs-space-2);
  font-size: 24px;
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.stat-value.danger {
  color: var(--bs-color-semantic-danger);
}

.stat-value.warning {
  color: var(--bs-color-semantic-warning);
}

.stat-unit {
  margin-left: var(--bs-space-1);
  font-size: var(--bs-typography-font-size-xs);
  font-weight: 400;
  color: var(--bs-color-fg-muted);
}

.chart-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--bs-space-3);
}

.chart-card {
  background: var(--bs-color-bg-surface);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  padding: var(--bs-space-3);
}

/* ECharts 容器必须有确定高度，不能用百分比 */
.chart-box {
  height: 320px;
}

.equipment-card {
  padding: var(--bs-space-3);
}

.card-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
  margin-bottom: var(--bs-space-2);
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.card-hint {
  font-size: var(--bs-typography-font-size-xs);
  font-weight: 400;
  color: var(--bs-color-fg-muted);
}

.card-alert {
  margin-bottom: var(--bs-space-2);
}

.util-cell {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.util-track {
  flex: 1;
  min-width: 60px;
  height: 8px;
  border-radius: var(--bs-radius-full);
  background: var(--bs-color-fill-lighter);
  overflow: hidden;
}

.util-fill {
  height: 100%;
  border-radius: var(--bs-radius-full);
  background: var(--bs-color-chart-1);
}

.util-fill.is-over {
  background: var(--bs-color-semantic-danger);
}

.util-num {
  min-width: 52px;
  text-align: right;
  color: var(--bs-color-fg-default);
}

.util-num.is-over {
  color: var(--bs-color-semantic-danger);
  font-weight: 600;
}

.conflict-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.conflict-item {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bs-space-3);
  align-items: baseline;
  padding: var(--bs-space-2);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-sm);
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-default);
}

.c-no {
  font-weight: 600;
}

.c-equipment,
.c-task,
.c-time {
  color: var(--bs-color-fg-secondary);
}

.c-reason {
  color: var(--bs-color-semantic-danger);
}

.detail-body {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.detail-section-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

@media (max-width: 767px) {
  .stat-cards {
    grid-template-columns: repeat(2, 1fr);
  }

  .chart-grid {
    grid-template-columns: 1fr;
  }

  .chart-box {
    height: 260px;
  }

  .filter-bar {
    gap: var(--bs-space-1);
  }
}
</style>
