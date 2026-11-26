<script setup lang="ts">
/**
 * 营收分析看板（B7 · CSV 第 3 项）。
 *
 * 口径与后端 `app/modules/sales/revenue_router.py` 一一对应：
 *   合同额 = 已审批通过合同金额合计（按合同签订日期归期）
 *   结算额 = 客户已确认结算单金额合计（按结算单建立日期归期）
 *   回款额 = 已确认到账回款单金额合计（按到账日期归期）
 * 三口径各自独立归期，**不可相加**；口径说明由服务端 caliber 下发。
 */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import PageHeader from '@/components/common/PageHeader.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import CustomerSelect from '@/components/form/CustomerSelect.vue'
import { useDictOptions } from '@/composables/useDict'
import {
  exportRevenue,
  getRevenueBoard,
  type RevenueBoard as RevenueBoardData,
  type RevenueQuery,
} from '@/api/sales'
import { chartPalette, resolveToken, watchChartTheme } from '@/utils/chartTheme'

defineOptions({ name: 'RevenueBoard' })

echarts.use([BarChart, LineChart, PieChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const { t, locale } = useI18n()

// ---------------- 筛选 ----------------

function fmtDate(d: Date): string {
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${d.getFullYear()}-${m}-${day}`
}

function defaultRange(): [string, string] {
  const to = new Date()
  const from = new Date(to.getFullYear(), to.getMonth() - 11, 1)
  return [fmtDate(from), fmtDate(to)]
}

const range = ref<string[]>(defaultRange())
const bizBlock = ref('')
const customerId = ref<number | null>(null)
const { opts: blockOpts } = useDictOptions('biz_block')

/** biz_block 编码 → 字典标签（随语言切换） */
const blockMap = computed<Record<string, string>>(() => {
  const m: Record<string, string> = {}
  for (const o of blockOpts.value) m[o.value] = o.label
  return m
})

function queryParams(): RevenueQuery {
  const p: RevenueQuery = {}
  const [from, to] = range.value ?? []
  if (from) p.from = from
  if (to) p.to = to
  if (bizBlock.value) p.biz_block = bizBlock.value
  if (customerId.value) p.customer_id = customerId.value
  return p
}

// ---------------- 数据 ----------------

const board = ref<RevenueBoardData | null>(null)
const loading = ref(false)
const exporting = ref(false)

async function load() {
  loading.value = true
  try {
    board.value = await getRevenueBoard(queryParams())
  } catch {
    /* http layer already notified */
  } finally {
    loading.value = false
  }
}

async function doExport() {
  exporting.value = true
  try {
    await exportRevenue(queryParams())
  } catch {
    /* http layer already notified */
  } finally {
    exporting.value = false
  }
}

onMounted(() => void load())

// ---------------- 展示工具 ----------------

function fmtAmount(v: unknown): string {
  const n = Number(v ?? 0)
  if (!Number.isFinite(n)) return '-'
  return n.toLocaleString(locale.value, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtShort(v: unknown): string {
  const n = Number(v ?? 0)
  if (!Number.isFinite(n)) return '-'
  if (Math.abs(n) < 10000) return n.toLocaleString(locale.value, { maximumFractionDigits: 0 })
  return locale.value === 'en-US'
    ? `${(n / 1000).toFixed(1)}K`
    : `${(n / 10000).toFixed(1)}w`
}

function fmtRate(v: unknown): string {
  const n = Number(v ?? 0)
  if (!Number.isFinite(n)) return '-'
  return `${n.toFixed(1)}%`
}

/** 业务线文案：unknown / multi 走 i18n，其余优先用前端字典（随语言切换），回落服务端文本 */
function blockLabel(code: string, text?: string): string {
  if (code === 'unknown') return t('sales.revenue.bizUnknown')
  if (code === 'multi') return t('sales.revenue.bizMulti')
  return blockMap.value[code] || text || code
}

const summary = computed(() => board.value?.summary ?? null)

const caliber = computed(() => {
  const b = board.value
  if (!b) return null
  return locale.value === 'en-US' ? (b.caliberEn ?? b.caliber) : b.caliber
})

// ---------------- 图表 ----------------

const trendEl = ref<HTMLElement | null>(null)
const blockEl = ref<HTMLElement | null>(null)
const rateEl = ref<HTMLElement | null>(null)
const charts: echarts.ECharts[] = []
let resizeObserver: ResizeObserver | null = null

function renderCharts() {
  const b = board.value
  charts.forEach((c) => c.dispose())
  charts.length = 0
  if (!b) return

  const palette = chartPalette()
  const c1 = palette[0] ?? ''
  const c2 = palette[1] ?? ''
  const c3 = palette[2] ?? ''
  const axisText = resolveToken('--bs-color-fg-muted', '#909399')
  const axis = {
    axisLabel: { color: axisText },
    axisLine: { lineStyle: { color: resolveToken('--bs-color-border-default', '#dcdfe6') } },
    splitLine: { lineStyle: { color: resolveToken('--bs-color-border-subtle', '#e4e7ed') } },
  }
  const surface = resolveToken('--bs-color-bg-surface', '#ffffff')

  if (trendEl.value) {
    const c = echarts.init(trendEl.value)
    c.setOption({
      tooltip: { trigger: 'axis', valueFormatter: (v: unknown) => fmtAmount(v) },
      legend: { bottom: 0, textStyle: { color: axisText } },
      grid: { left: 64, right: 24, top: 24, bottom: 56 },
      xAxis: { type: 'category', data: b.byMonth.map((m) => m.month), ...axis },
      yAxis: {
        type: 'value',
        ...axis,
        axisLabel: { color: axisText, formatter: (v: number) => fmtShort(v) },
      },
      series: [
        {
          name: t('sales.revenue.series.contractAmount'),
          type: 'line',
          smooth: true,
          itemStyle: { color: c1 },
          areaStyle: { opacity: 0.12 },
          data: b.byMonth.map((m) => m.contractAmount),
        },
        {
          name: t('sales.revenue.series.settledAmount'),
          type: 'line',
          smooth: true,
          itemStyle: { color: c2 },
          data: b.byMonth.map((m) => m.settledAmount),
        },
        {
          name: t('sales.revenue.series.receivedAmount'),
          type: 'line',
          smooth: true,
          itemStyle: { color: c3 },
          data: b.byMonth.map((m) => m.receivedAmount),
        },
      ],
    })
    charts.push(c)
  }

  if (blockEl.value) {
    const c = echarts.init(blockEl.value)
    c.setOption({
      tooltip: { trigger: 'item', valueFormatter: (v: unknown) => fmtAmount(v) },
      legend: { bottom: 0, type: 'scroll', textStyle: { color: axisText } },
      series: [
        {
          type: 'pie',
          radius: ['40%', '66%'],
          center: ['50%', '45%'],
          itemStyle: { borderColor: surface, borderWidth: 2 },
          label: { formatter: '{b}\n{d}%' },
          data: b.byBizBlock.map((x) => ({
            name: blockLabel(x.bizBlock, x.bizBlockText),
            value: x.contractAmount,
          })),
        },
      ],
    })
    charts.push(c)
  }

  if (rateEl.value) {
    const c = echarts.init(rateEl.value)
    c.setOption({
      tooltip: { trigger: 'axis', valueFormatter: (v: unknown) => fmtRate(v) },
      legend: { bottom: 0, textStyle: { color: axisText } },
      grid: { left: 56, right: 24, top: 24, bottom: 72 },
      xAxis: {
        type: 'category',
        data: b.byBizBlock.map((x) => blockLabel(x.bizBlock, x.bizBlockText)),
        ...axis,
        axisLabel: { rotate: 20, color: axisText },
      },
      yAxis: {
        type: 'value',
        max: 100,
        ...axis,
        axisLabel: { color: axisText, formatter: '{value}%' },
      },
      series: [
        {
          name: t('sales.revenue.series.collectionRate'),
          type: 'bar',
          barWidth: 22,
          itemStyle: { color: c1, borderRadius: [4, 4, 0, 0] },
          data: b.byBizBlock.map((x) => x.collectionRate),
        },
        {
          name: t('sales.revenue.series.receivableRate'),
          type: 'bar',
          barWidth: 22,
          itemStyle: { color: c2, borderRadius: [4, 4, 0, 0] },
          data: b.byBizBlock.map((x) => x.receivableRate),
        },
      ],
    })
    charts.push(c)
  }
}

watch(board, () => requestAnimationFrame(renderCharts))
watch(blockOpts, () => requestAnimationFrame(renderCharts))
watchChartTheme(() => renderCharts())

onMounted(() => {
  resizeObserver = new ResizeObserver(() => charts.forEach((c) => c.resize()))
  ;[trendEl.value, blockEl.value, rateEl.value].forEach((el) => el && resizeObserver?.observe(el))
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  charts.forEach((c) => c.dispose())
})

// ---------------- 明细表 ----------------

const customerColumns: ListColumn[] = [
  { prop: 'customerName', labelKey: 'sales.revenue.table.customer', minWidth: 170 },
  {
    prop: 'contractAmount',
    labelKey: 'sales.revenue.series.contractAmount',
    width: 140,
    align: 'right',
    formatter: (r) => fmtAmount(r.contractAmount),
  },
  {
    prop: 'settledAmount',
    labelKey: 'sales.revenue.series.settledAmount',
    width: 140,
    align: 'right',
    formatter: (r) => fmtAmount(r.settledAmount),
  },
  {
    prop: 'receivedAmount',
    labelKey: 'sales.revenue.series.receivedAmount',
    width: 140,
    align: 'right',
    formatter: (r) => fmtAmount(r.receivedAmount),
  },
  {
    prop: 'contractCount',
    labelKey: 'sales.revenue.table.contractCount',
    width: 100,
    align: 'right',
    formatter: (r) => String(r.contractCount ?? 0),
  },
  { prop: 'bizBlocks', labelKey: 'sales.revenue.table.bizBlocks', minWidth: 150, slot: 'bizBlocks' },
  {
    prop: 'collectionRate',
    labelKey: 'sales.revenue.table.collectionRate',
    width: 120,
    align: 'right',
    formatter: (r) => fmtRate(r.collectionRate),
  },
]

const contractColumns: ListColumn[] = [
  { prop: 'contractNo', labelKey: 'sales.revenue.table.contractNo', width: 160 },
  { prop: 'contractName', labelKey: 'sales.revenue.table.contractName', minWidth: 200 },
  { prop: 'customerName', labelKey: 'sales.revenue.table.customer', minWidth: 150 },
  { prop: 'bizBlockText', labelKey: 'sales.revenue.bizBlock', width: 130, slot: 'bizBlock' },
  {
    prop: 'amount',
    labelKey: 'sales.revenue.series.contractAmount',
    width: 140,
    align: 'right',
    formatter: (r) => fmtAmount(r.amount),
  },
  {
    prop: 'settledAmount',
    labelKey: 'sales.revenue.series.settledAmount',
    width: 140,
    align: 'right',
    formatter: (r) => fmtAmount(r.settledAmount),
  },
  {
    prop: 'receivedAmount',
    labelKey: 'sales.revenue.series.receivedAmount',
    width: 140,
    align: 'right',
    formatter: (r) => fmtAmount(r.receivedAmount),
  },
  { prop: 'signDate', labelKey: 'sales.revenue.table.signDate', width: 120 },
  {
    prop: 'collectionRate',
    labelKey: 'sales.revenue.table.collectionRate',
    width: 120,
    align: 'right',
    formatter: (r) => fmtRate(r.collectionRate),
  },
]

const customerRows = computed(() => (board.value?.byCustomer ?? []) as unknown as Record<string, unknown>[])
const contractRows = computed(() => (board.value?.byContract ?? []) as unknown as Record<string, unknown>[])

/** 表格 slot 辅助：避免在模板里做类型断言 */
function bizBlocksOf(row: Record<string, unknown>): string[] {
  const codes = row.bizBlockCodes
  if (Array.isArray(codes)) return codes.map((c) => blockLabel(String(c)))
  const texts = row.bizBlocks
  return Array.isArray(texts) ? texts.map((x) => String(x)) : []
}

function blockOf(row: Record<string, unknown>): string {
  const text = row.bizBlockText
  return blockLabel(String(row.bizBlock ?? ''), typeof text === 'string' ? text : undefined)
}
</script>

<template>
  <div class="bs-page bs-page--scroll revenue-board">
    <PageHeader :title="t('sales.revenue.title')">
      <template #actions>
        <el-button :loading="loading" @click="load">{{ t('sales.revenue.refresh') }}</el-button>
        <el-button
          v-permission="'sales:revenue:view'"
          type="primary"
          :loading="exporting"
          @click="doExport"
        >
          {{ t('sales.revenue.export') }}
        </el-button>
      </template>
    </PageHeader>

    <p class="page-sub">{{ t('sales.revenue.subtitle') }}</p>

    <!-- 筛选 -->
    <el-card shadow="never" class="filter-card">
      <div class="filter-row">
        <div class="filter-item">
          <div class="filter-label">{{ t('sales.revenue.range') }}</div>
          <el-date-picker
            v-model="range"
            type="daterange"
            value-format="YYYY-MM-DD"
            :clearable="false"
            :start-placeholder="t('sales.revenue.rangeStart')"
            :end-placeholder="t('sales.revenue.rangeEnd')"
          />
        </div>
        <div class="filter-item">
          <div class="filter-label">{{ t('sales.revenue.bizBlock') }}</div>
          <el-select
            v-model="bizBlock"
            clearable
            :placeholder="t('sales.revenue.bizBlockAll')"
            class="filter-select"
          >
            <el-option v-for="o in blockOpts" :key="o.value" :label="o.label" :value="o.value" />
          </el-select>
        </div>
        <div class="filter-item">
          <div class="filter-label">{{ t('sales.revenue.customer') }}</div>
          <CustomerSelect
            v-model="customerId"
            :placeholder="t('sales.revenue.customerAll')"
            width="220px"
          />
        </div>
      </div>
    </el-card>

    <div v-loading="loading">
      <!-- 统计卡片 -->
      <div v-if="summary" class="stat-cards">
        <div class="stat-card">
          <div class="stat-label">{{ t('sales.revenue.summary.contractAmount') }}</div>
          <div class="stat-value">
            {{ fmtAmount(summary.contractAmount) }}<span class="stat-unit">{{ t('sales.revenue.amountUnit') }}</span>
          </div>
          <div class="stat-meta">
            {{ t('sales.revenue.summary.contractCount') }}: {{ summary.contractCount }} ·
            {{ t('sales.revenue.summary.customerCount') }}: {{ summary.customerCount }} ·
            {{ t('sales.revenue.summary.avgContractAmount') }}: {{ fmtAmount(summary.avgContractAmount) }}
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('sales.revenue.summary.settledAmount') }}</div>
          <div class="stat-value">
            {{ fmtAmount(summary.settledAmount) }}<span class="stat-unit">{{ t('sales.revenue.amountUnit') }}</span>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('sales.revenue.summary.receivedAmount') }}</div>
          <div class="stat-value">
            {{ fmtAmount(summary.receivedAmount) }}<span class="stat-unit">{{ t('sales.revenue.amountUnit') }}</span>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('sales.revenue.summary.unsettledAmount') }}</div>
          <div class="stat-value">
            {{ fmtAmount(summary.unsettledAmount) }}<span class="stat-unit">{{ t('sales.revenue.amountUnit') }}</span>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('sales.revenue.summary.unreceivedAmount') }}</div>
          <div class="stat-value">
            {{ fmtAmount(summary.unreceivedAmount) }}<span class="stat-unit">{{ t('sales.revenue.amountUnit') }}</span>
          </div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('sales.revenue.summary.receivableRate') }}</div>
          <div class="stat-value">
            {{ summary.receivableRate.toFixed(1) }}<span class="stat-unit">{{ t('sales.revenue.rateUnit') }}</span>
          </div>
          <div class="stat-meta">
            {{ t('sales.revenue.table.collectionRate') }}: {{ summary.collectionRate.toFixed(1) }}%
          </div>
        </div>
      </div>

      <!-- 图表 -->
      <div class="chart-grid">
        <div class="chart-card chart-wide">
          <div class="chart-title">{{ t('sales.revenue.chart.trend') }}</div>
          <div ref="trendEl" class="chart-box" />
        </div>
        <div class="chart-card">
          <div class="chart-title">{{ t('sales.revenue.chart.byBlock') }}</div>
          <div ref="blockEl" class="chart-box" />
        </div>
        <div class="chart-card">
          <div class="chart-title">{{ t('sales.revenue.chart.rate') }}</div>
          <div ref="rateEl" class="chart-box" />
        </div>
      </div>

      <!-- 明细 -->
      <el-card shadow="never" class="detail-card">
        <el-tabs>
          <el-tab-pane :label="t('sales.revenue.table.customerTitle')">
            <ListTable
              :columns="customerColumns"
              :data="customerRows"
              :show-pagination="false"
              row-key="customerId"
            >
              <template #bizBlocks="{ row }">
                <div class="tag-row">
                  <el-tag
                    v-for="(b, i) in bizBlocksOf(row)"
                    :key="`${b}-${i}`"
                    size="small"
                    type="info"
                    effect="plain"
                  >
                    {{ b }}
                  </el-tag>
                </div>
              </template>
            </ListTable>
          </el-tab-pane>
          <el-tab-pane :label="t('sales.revenue.table.contractTitle')">
            <ListTable
              :columns="contractColumns"
              :data="contractRows"
              :show-pagination="false"
              row-key="contractId"
            >
              <template #bizBlock="{ row }">
                {{ blockOf(row) }}
              </template>
            </ListTable>
          </el-tab-pane>
        </el-tabs>
      </el-card>

      <!-- 口径说明 -->
      <el-card shadow="never" class="caliber-card">
        <template #header>
          <div class="card-title">{{ t('sales.revenue.caliber.title') }}</div>
        </template>
        <el-alert
          :title="t('sales.revenue.caliber.tip')"
          type="warning"
          :closable="false"
          show-icon
        />
        <ul v-if="caliber" class="caliber-list">
          <li>
            <span class="caliber-name">{{ t('sales.revenue.caliber.contractAmount') }}</span>
            <span class="caliber-text">{{ caliber.contractAmount }}</span>
          </li>
          <li>
            <span class="caliber-name">{{ t('sales.revenue.caliber.settledAmount') }}</span>
            <span class="caliber-text">{{ caliber.settledAmount }}</span>
          </li>
          <li>
            <span class="caliber-name">{{ t('sales.revenue.caliber.receivedAmount') }}</span>
            <span class="caliber-text">{{ caliber.receivedAmount }}</span>
          </li>
        </ul>
      </el-card>
    </div>
  </div>
</template>

<style scoped>
.filter-card,
.detail-card,
.caliber-card {
  margin-bottom: var(--bs-space-3);
}

.page-sub {
  margin: 0 0 var(--bs-space-3);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs, 12px);
}

.filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bs-space-3);
  align-items: flex-end;
}

.filter-item {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-1);
}

.filter-label {
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-xs, 12px);
}

.filter-select {
  width: 200px;
}

.stat-cards {
  display: grid;
  grid-template-columns: repeat(6, 1fr);
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
  font-size: 22px;
  font-weight: 600;
  color: var(--bs-color-fg-default);
  word-break: break-all;
}

.stat-unit {
  margin-left: var(--bs-space-1);
  font-size: var(--bs-typography-font-size-xs, 12px);
  font-weight: 400;
  color: var(--bs-color-fg-muted);
}

.stat-meta {
  margin-top: var(--bs-space-1);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs, 12px);
}

.chart-grid {
  margin-top: var(--bs-space-3);
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

/* 图表容器高度写死 px：ECharts 初始化时读容器高度，百分比高度会塌陷 */
.chart-box {
  height: 300px;
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bs-space-1);
}

.card-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.caliber-list {
  margin: var(--bs-space-3) 0 0;
  padding-left: var(--bs-space-4);
  color: var(--bs-color-fg-secondary);
}

.caliber-list li {
  margin-bottom: var(--bs-space-1);
  line-height: 1.6;
}

.caliber-name {
  margin-right: var(--bs-space-2);
  color: var(--bs-color-fg-default);
  font-weight: 600;
}

@media (max-width: 767px) {
  .stat-cards {
    grid-template-columns: repeat(2, 1fr);
  }

  .chart-grid {
    grid-template-columns: 1fr;
  }

  .chart-wide {
    grid-column: auto;
  }
}
</style>
