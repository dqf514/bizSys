<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ApprovalTimeline from '@/components/approval/ApprovalTimeline.vue'
import ApprovalActionbar from '@/components/approval/ApprovalActionbar.vue'
import { useListPage } from '@/composables/useListPage'
import { listApprovalTasks, getTimeline, getInstance, type ApprovalTab } from '@/api/approval'
import type { ApprovalTask, TimelineRecord } from '@/api/types'

defineOptions({ name: 'TodoList' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'approval.approval.titleField', width: 220 },
]

const statusTabs: StatusTabItem[] = [
  { value: 'todo', labelKey: 'approval.approval.tabTodo' },
  { value: 'done', labelKey: 'approval.approval.tabDone' },
  { value: 'initiated', labelKey: 'approval.approval.tabInitiated' },
]

const list = useListPage<ApprovalTask>({
  fetch: async (params) => {
    const tab = (params.status as ApprovalTab) || 'todo'
    const data = await listApprovalTasks(tab, {
      ...params,
      status: undefined,
      q: searchModel.value.q || undefined,
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  defaultStatus: 'todo',
})

const columns: ListColumn[] = [
  { prop: 'title', labelKey: 'approval.approval.titleField', minWidth: 220, fixed: 'left' },
  { prop: 'bizType', labelKey: 'approval.approval.bizType', width: 100 },
  { prop: 'nodeName', labelKey: 'approval.approval.nodeName', width: 120 },
  { prop: 'status', labelKey: 'approval.approval.status', width: 100 },
  { prop: 'initiatorName', labelKey: 'approval.approval.initiatorName', width: 110 },
  { prop: 'assigneeName', labelKey: 'approval.approval.assigneeName', width: 110 },
  { prop: 'createTime', labelKey: 'approval.approval.createTime', width: 160 },
  { prop: 'actedAt', labelKey: 'approval.approval.actedAt', width: 160 },
]

const drawerVisible = ref(false)
const current = ref<ApprovalTask | null>(null)
const records = ref<TimelineRecord[]>([])
const timelineLoading = ref(false)
const snapshot = ref<Record<string, unknown> | null>(null)
const snapshotLoading = ref(false)

async function openDetail(row: ApprovalTask) {
  current.value = row
  drawerVisible.value = true
  timelineLoading.value = true
  snapshotLoading.value = true
  snapshot.value = null
  try {
    const tl = await getTimeline(row.bizType, row.bizId)
    records.value = tl.records ?? []
  } catch {
    records.value = []
  } finally {
    timelineLoading.value = false
  }
  try {
    const inst = await getInstance(row.instanceId)
    snapshot.value = inst.snapshot ?? null
  } catch {
    snapshot.value = null
  } finally {
    snapshotLoading.value = false
  }
}

/** snake_case / camelCase 字段名转可读标签 */
function snapshotLabel(key: string) {
  const words = key
    .replace(/_/g, ' ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

function snapshotValue(v: unknown): string {
  if (v === null || v === undefined || v === '') return '-'
  if (typeof v === 'object') return JSON.stringify(v, null, 2)
  return String(v)
}

function onDone() {
  drawerVisible.value = false
  list.refresh()
}

function bizTypeLabel(bt: string) {
  if (bt === 'contract') return t('approval.approval.bizContract')
  if (bt === 'task') return t('approval.approval.bizTask')
  return bt
}

watch(
  () => list.query.status,
  () => {
    /* status tab drives approval tab via fetch */
  },
)

onMounted(() => {
  /* first load handled by useListPage */
})
</script>

<template>
  <ListPage :title="t('approval.approval.title')" :loading="list.loading.value">
    <template #actions>
      <el-button @click="list.refresh()">{{ t('common.action.refresh') }}</el-button>
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '' }; list.reset()"
      />
    </template>

    <template #statusTabs>
      <StatusTabs
        :tabs="statusTabs"
        :model-value="String(list.query.status)"
        @update:model-value="list.setStatus($event)"
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
        row-key="id"
        @update:page="list.setPage"
        @update:size="list.setSize"
      >
        <template #bizType="{ row }">{{ bizTypeLabel(String(row.bizType)) }}</template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="approval.approval.status" />
        </template>
        <template #title="{ row }">
          <el-button link type="primary" @click="openDetail(row as unknown as ApprovalTask)">{{ row.title }}</el-button>
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="110" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openDetail(row as unknown as ApprovalTask)">
                {{ t('common.action.detail') }}
              </el-button>
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-drawer v-model="drawerVisible" :title="t('approval.approval.detail')" size="520px">
    <div v-if="current" class="drawer-body">
      <el-descriptions :column="1" border>
        <el-descriptions-item :label="t('approval.approval.titleField')">{{ current.title }}</el-descriptions-item>
        <el-descriptions-item :label="t('approval.approval.bizType')">{{ bizTypeLabel(current.bizType) }}</el-descriptions-item>
        <el-descriptions-item :label="t('approval.approval.nodeName')">{{ current.nodeName }}</el-descriptions-item>
        <el-descriptions-item :label="t('approval.approval.initiatorName')">{{ current.initiatorName }}</el-descriptions-item>
        <el-descriptions-item :label="t('approval.approval.comment')">{{ current.comment || '-' }}</el-descriptions-item>
      </el-descriptions>

      <div class="section-title">{{ t('approval.approval.timeline') }}</div>
      <ApprovalTimeline :records="records" :loading="timelineLoading" />

      <template v-if="snapshot && Object.keys(snapshot).length">
        <div class="section-title">{{ t('approval.approval.formSnapshot') }}</div>
        <el-descriptions :column="1" border v-loading="snapshotLoading">
          <el-descriptions-item v-for="(v, k) in snapshot" :key="k" :label="snapshotLabel(String(k))">
            <pre v-if="typeof v === 'object' && v !== null" class="snapshot-json">{{ snapshotValue(v) }}</pre>
            <template v-else>{{ snapshotValue(v) }}</template>
          </el-descriptions-item>
        </el-descriptions>
      </template>

      <div class="section-title">{{ t('approval.approval.detail') }}</div>
      <ApprovalActionbar
        :task="current"
        :can-act="String(list.query.status) === 'todo'"
        :can-withdraw="String(list.query.status) === 'initiated'"
        @done="onDone"
      />
    </div>
  </el-drawer>
</template>

<style scoped>
.drawer-body {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.section-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.snapshot-json {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-all;
  font-size: var(--bs-typography-font-size-xs);
}
</style>
