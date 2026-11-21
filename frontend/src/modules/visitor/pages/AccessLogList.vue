<script setup lang="ts">
/** 合规审计日志（B3）：只读视图 —— 不可删改，保留期 ≥180 天；附通行应急报表。 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import { useListPage } from '@/composables/useListPage'
import { exportVisitorAccessLogs, listVisitorAccessLogs, visitorAccessLogSummary } from '@/api/visitor'
import type { VisitorAccessLog, VisitorAccessLogSummary } from '@/api/types'

defineOptions({ name: 'AccessLogList' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '', result: '' })
const searchFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'visitor.audit.searchName',
    placeholderKey: 'visitor.audit.placeholderName',
    width: 280,
  },
  {
    key: 'result',
    labelKey: 'visitor.audit.result',
    type: 'select',
    options: [
      { label: t('visitor.audit.resultPass'), value: 'pass' },
      { label: t('visitor.audit.resultDeny'), value: 'deny' },
    ],
    width: 140,
  },
])

function buildFilters(params: Record<string, unknown>) {
  return {
    ...((params.filters as Record<string, unknown>) || {}),
    result: searchModel.value.result || undefined,
  }
}

const list = useListPage<VisitorAccessLog>({
  fetch: async (params) => {
    const data = await listVisitorAccessLogs({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(params),
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportVisitorAccessLogs({
      ...params,
      q: searchModel.value.q || undefined,
      filters: buildFilters(params),
    }),
  defaultStatus: 'all',
})

const columns: ListColumn[] = [
  { prop: 'happenedAt', labelKey: 'visitor.audit.happenedAt', width: 165, fixed: 'left', sortable: 'happened_at' },
  { prop: 'visitorName', labelKey: 'visitor.audit.visitorName', width: 110 },
  { prop: 'credentialNo', labelKey: 'visitor.audit.credentialNo', width: 170 },
  { prop: 'zoneName', labelKey: 'visitor.audit.zoneName', width: 140 },
  { prop: 'eventType', labelKey: 'visitor.audit.eventType', width: 120 },
  { prop: 'method', labelKey: 'visitor.audit.method', width: 100 },
  { prop: 'result', labelKey: 'visitor.audit.result', width: 90, sortable: 'result' },
  { prop: 'deviceId', labelKey: 'visitor.audit.deviceId', width: 120 },
  { prop: 'operatorName', labelKey: 'visitor.audit.operatorName', width: 110 },
  { prop: 'detail', labelKey: 'visitor.audit.detail', minWidth: 180 },
]

/* ---------------- 应急报表 ---------------- */
const summary = ref<VisitorAccessLogSummary | null>(null)
const summaryDays = ref(7)

async function loadSummary() {
  try {
    summary.value = await visitorAccessLogSummary(summaryDays.value)
  } catch {
    /* optional */
  }
}

onMounted(() => void loadSummary())

function eventText(type: string) {
  const key = `visitor.audit.event${type
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join('')}`
  const label = t(key)
  return label === key ? type : label
}
</script>

<template>
  <ListPage :title="t('visitor.audit.title')" :loading="list.loading.value">
    <template #actions>
      <el-button @click="loadSummary">{{ t('common.action.refresh') }}</el-button>
      <ExportButton v-permission="'visitor:audit:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', result: '' }; list.reset()"
      />
    </template>

    <template #toolbar>
      <el-alert type="info" :closable="false" show-icon :title="t('visitor.audit.readonlyTip')" />
    </template>

    <template #table>
      <el-table
        v-if="summary"
        class="audit-summary"
        :data="Object.entries(summary.byEvent).map(([k, v]) => ({ type: k, count: v }))"
        size="small"
        border
      >
        <el-table-column prop="type" :label="t('visitor.audit.eventType')" />
        <el-table-column prop="count" :label="t('visitor.audit.reportTotal')" width="120" align="center" />
      </el-table>

      <ListTable
        :columns="columns"
        :data="list.items.value as unknown as Record<string, unknown>[]"
        :loading="list.loading.value"
        :total="list.total.value"
        :page="Number(list.query.page)"
        :size="Number(list.query.size)"
        row-key="id"
        @update:page="list.setPage"
        @update:size="list.setSize"
        @sort-change="list.onSortChange"
      >
        <template #eventType="{ row }">
          {{ eventText(String(row.eventType)) }}
        </template>
        <template #result="{ row }">
          <el-tag
            :type="row.result === 'pass' ? 'success' : 'danger'"
            size="small"
            effect="light"
            round
          >
            {{ row.result === 'pass' ? t('visitor.audit.resultPass') : t('visitor.audit.resultDeny') }}
          </el-tag>
        </template>
      </ListTable>
    </template>
  </ListPage>
</template>

<style scoped>
.audit-summary {
  margin-bottom: var(--bs-space-2);
}
</style>
