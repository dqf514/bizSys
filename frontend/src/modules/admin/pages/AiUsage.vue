<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import * as echarts from 'echarts/core'
import { BarChart, LineChart } from 'echarts/charts'
import { GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import { CanvasRenderer } from 'echarts/renderers'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import { useListPage } from '@/composables/useListPage'
import { exportAiUsage, getAiStats, listAiUsage } from '@/api/ai'
import type { AiUsageRow, AiUsageStats } from '@/api/types'

defineOptions({ name: 'AiUsage' })

echarts.use([BarChart, LineChart, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])

const { t } = useI18n()

// ---------------- 统计（SQL 聚合） ----------------

const days = ref(30)
const stats = ref<AiUsageStats | null>(null)
const statsLoading = ref(false)

async function loadStats() {
  statsLoading.value = true
  try {
    stats.value = await getAiStats(days.value)
  } catch {
    /* http layer already notified */
  } finally {
    statsLoading.value = false
  }
}

function featureLabel(f: string) {
  const key = `ai.feature.${f}`
  const tr = t(key)
  return tr === key ? f : tr
}

const trendEl = ref<HTMLElement | null>(null)
const byFeatureEl = ref<HTMLElement | null>(null)
const byModelEl = ref<HTMLElement | null>(null)
const charts: echarts.ECharts[] = []
let resizeObserver: ResizeObserver | null = null

function renderCharts() {
  const s = stats.value
  if (!s) return
  charts.forEach((c) => c.dispose())
  charts.length = 0

  if (trendEl.value) {
    const c = echarts.init(trendEl.value)
    c.setOption({
      tooltip: { trigger: 'axis' },
      legend: { bottom: 0 },
      grid: { left: 48, right: 48, top: 24, bottom: 48 },
      xAxis: { type: 'category', data: s.trend.map((p) => p.date.slice(5)) },
      yAxis: [{ type: 'value', minInterval: 1 }, { type: 'value' }],
      series: [
        {
          name: t('ai.usage.calls'),
          type: 'line',
          smooth: true,
          areaStyle: { opacity: 0.15 },
          itemStyle: { color: '#409eff' },
          data: s.trend.map((p) => p.calls),
        },
        {
          name: 'Tokens',
          type: 'bar',
          yAxisIndex: 1,
          itemStyle: { color: '#67c23a', opacity: 0.55 },
          data: s.trend.map((p) => p.tokens),
        },
      ],
    })
    charts.push(c)
  }
  if (byFeatureEl.value) {
    const c = echarts.init(byFeatureEl.value)
    c.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 16, top: 24, bottom: 28 },
      xAxis: { type: 'category', data: s.byFeature.map((r) => featureLabel(r.feature)) },
      yAxis: { type: 'value', minInterval: 1 },
      series: [
        {
          type: 'bar',
          barWidth: 32,
          itemStyle: { color: '#409eff', borderRadius: [4, 4, 0, 0] },
          data: s.byFeature.map((r) => r.calls),
        },
      ],
    })
    charts.push(c)
  }
  if (byModelEl.value) {
    const c = echarts.init(byModelEl.value)
    c.setOption({
      tooltip: { trigger: 'axis' },
      grid: { left: 40, right: 16, top: 24, bottom: 60 },
      xAxis: { type: 'category', data: s.byModel.map((r) => r.model), axisLabel: { rotate: 20 } },
      yAxis: { type: 'value', minInterval: 1 },
      series: [
        {
          type: 'bar',
          barWidth: 32,
          itemStyle: { color: '#e6a23c', borderRadius: [4, 4, 0, 0] },
          data: s.byModel.map((r) => r.calls),
        },
      ],
    })
    charts.push(c)
  }
}

watch(stats, () => requestAnimationFrame(renderCharts))
watch(days, () => void loadStats())

onMounted(() => {
  void loadStats()
  resizeObserver = new ResizeObserver(() => charts.forEach((c) => c.resize()))
  ;[trendEl.value, byFeatureEl.value, byModelEl.value].forEach((el) => el && resizeObserver?.observe(el))
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  charts.forEach((c) => c.dispose())
})

// ---------------- 明细列表 ----------------

const searchModel = ref<Record<string, unknown>>({ q: '', feature: '', status: '', dateRange: null })

const featureOptions = computed(() =>
  ['quote', 'contract_ocr', 'task_photo', 'report_summary'].map((f) => ({ label: featureLabel(f), value: f })),
)
const statusOptions = computed(() =>
  ['success', 'error', 'fallback'].map((s) => ({ label: t(`ai.status.${s}`), value: s })),
)

const searchFields = computed<SearchField[]>(() => [
  { key: 'q', labelKey: 'ai.usage.user', placeholderKey: 'ai.usage.searchPlaceholder', width: 180 },
  { key: 'feature', labelKey: 'ai.usage.featureCol', type: 'select', options: featureOptions.value, width: 160 },
  { key: 'status', labelKey: 'ai.usage.statusCol', type: 'select', options: statusOptions.value, width: 140 },
  { key: 'dateRange', labelKey: 'ai.usage.time', type: 'daterange', width: 260 },
])

function rangeParam(): Record<string, string> {
  const dr = searchModel.value.dateRange as [string, string] | null
  return dr && dr[0] && dr[1] ? { create_time: `${dr[0]}|${dr[1]}` } : {}
}

function listParams() {
  return {
    q: (searchModel.value.q as string) || undefined,
    filters: {
      feature: (searchModel.value.feature as string) || undefined,
      status: (searchModel.value.status as string) || undefined,
    },
    range: rangeParam(),
  }
}

const list = useListPage<AiUsageRow>({
  fetch: async (params) => {
    const data = await listAiUsage({ ...params, ...listParams() })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
})

const columns: ListColumn[] = [
  { prop: 'createTime', labelKey: 'ai.usage.time', width: 160, sortable: 'create_time' },
  { prop: 'userName', labelKey: 'ai.usage.user', width: 110, sortable: 'user_name' },
  { prop: 'feature', labelKey: 'ai.usage.featureCol', width: 120, slot: 'feature' },
  { prop: 'model', labelKey: 'ai.usage.model', minWidth: 140, showOverflowTooltip: true },
  { prop: 'totalTokens', labelKey: 'ai.usage.tokens', width: 100, align: 'right' },
  { prop: 'durationMs', labelKey: 'ai.usage.duration', width: 90, align: 'right', formatter: (r) => `${r.durationMs} ms` },
  { prop: 'status', labelKey: 'ai.usage.statusCol', width: 90, slot: 'status' },
  { prop: 'error', labelKey: 'ai.usage.errorCol', minWidth: 180, showOverflowTooltip: true },
  {
    prop: 'biz',
    labelKey: 'ai.usage.biz',
    width: 150,
    formatter: (r) => (r.bizType ? `${r.bizType}${r.bizId ? ` #${r.bizId}` : ''}` : '-'),
  },
]

function statusTagType(s: string) {
  return s === 'success' ? 'success' : s === 'error' ? 'danger' : 'warning'
}
</script>

<template>
  <div class="ai-usage-page">
    <div class="stats-block" v-loading="statsLoading">
      <div class="stat-cards" v-if="stats">
        <div class="stat-card">
          <div class="stat-label">{{ t('ai.usage.totalCalls') }}</div>
          <div class="stat-value">{{ stats.cards.totalCalls }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('ai.usage.successRate') }}</div>
          <div class="stat-value">{{ stats.cards.successRate }}<span class="stat-unit">%</span></div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('ai.usage.totalTokens') }}</div>
          <div class="stat-value">{{ stats.cards.totalTokens.toLocaleString() }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('ai.usage.activeUsers') }}</div>
          <div class="stat-value">{{ stats.cards.activeUsers }}</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">{{ t('ai.usage.avgDuration') }}</div>
          <div class="stat-value">
            {{ stats.cards.avgDurationMs }}<span class="stat-unit">{{ t('ai.usage.ms') }}</span>
          </div>
        </div>
      </div>

      <div class="chart-grid" v-if="stats">
        <div class="chart-card chart-wide">
          <div class="chart-head">
            <div class="chart-title">{{ t('ai.usage.trend', { days: stats.days }) }}</div>
            <el-radio-group v-model="days" size="small" class="days-switch">
              <el-radio-button :value="7">7</el-radio-button>
              <el-radio-button :value="30">30</el-radio-button>
              <el-radio-button :value="90">90</el-radio-button>
            </el-radio-group>
          </div>
          <div ref="trendEl" class="chart-box" />
        </div>
        <div class="chart-card">
          <div class="chart-title">{{ t('ai.usage.byFeature') }}</div>
          <div ref="byFeatureEl" class="chart-box" />
        </div>
        <div class="chart-card">
          <div class="chart-title">{{ t('ai.usage.byModel') }}</div>
          <div ref="byModelEl" class="chart-box" />
        </div>
        <div class="chart-card chart-wide" v-if="stats.byUser.length">
          <div class="chart-title">{{ t('ai.usage.byUser') }}</div>
          <el-table :data="stats.byUser" size="small" class="byuser-table">
            <el-table-column prop="userName" :label="t('ai.usage.user')" />
            <el-table-column prop="calls" :label="t('ai.usage.calls')" width="140" align="right" />
            <el-table-column prop="tokens" label="Tokens" width="180" align="right" />
          </el-table>
        </div>
      </div>
    </div>

    <ListPage :title="t('ai.usage.detail')" :loading="list.loading.value" class="detail-block">
      <template #actions>
        <ExportButton
          v-permission="'admin:ai:usage:export'"
          :export-fn="() => exportAiUsage(listParams())"
        />
        <el-button @click="list.refresh()">{{ t('common.action.refresh') }}</el-button>
      </template>

      <template #searchBar>
        <SearchBar
          v-model="searchModel"
          :fields="searchFields"
          @search="list.search()"
          @reset="searchModel = { q: '', feature: '', status: '', dateRange: null }; list.reset()"
        />
      </template>

      <template #table>
        <ListTable
          :columns="columns"
          :data="list.items.value as unknown as Record<string, unknown>[]"
          :loading="list.loading.value"
          :total="list.total.value"
          :page="Number(list.query.page)"
          :size="Number(list.query.size)"
          @update:page="list.setPage"
          @update:size="list.setSize"
          @sort-change="list.onSortChange"
        >
          <template #feature="{ row }">
            {{ featureLabel((row as unknown as AiUsageRow).feature) }}
          </template>
          <template #status="{ row }">
            <el-tag :type="statusTagType((row as unknown as AiUsageRow).status)" size="small">
              {{ t(`ai.status.${(row as unknown as AiUsageRow).status}`) }}
            </el-tag>
          </template>
        </ListTable>
      </template>
    </ListPage>
  </div>
</template>

<style scoped>
.ai-usage-page {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
  height: 100%;
  min-height: 0;
  overflow: auto;
}

.detail-block {
  flex: 1;
  min-height: 320px;
}

.stat-cards {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
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
  font-size: 24px;
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

.chart-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.chart-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
  margin-bottom: var(--bs-space-2);
}

.chart-box {
  height: 240px;
}

.byuser-table {
  max-height: 260px;
}
</style>
