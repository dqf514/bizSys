<script setup lang="ts">
/** 流程中心：我的待办 / 我发起的（未读进度角标） / 抄送我的 / 已办。 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ApprovalTimeline from '@/components/approval/ApprovalTimeline.vue'
import ApprovalActionbar from '@/components/approval/ApprovalActionbar.vue'
import FlowGraphViewer from '@/components/flow/FlowGraphViewer.vue'
import { useListPage } from '@/composables/useListPage'
import {
  exportApprovalTasks,
  getInstance,
  getTimeline,
  listApprovalTasks,
  listCcItems,
  markCcRead,
  type ApprovalTab,
} from '@/api/approval'
import type { ApprovalInstanceDetail, ApprovalTask, TimelineRecord } from '@/api/types'

defineOptions({ name: 'TodoList' })

type CenterTab = ApprovalTab | 'cc'

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'approval.approval.titleField', width: 220 },
]

const activeTab = ref<CenterTab>('todo')
const todoCount = ref<number | undefined>(undefined)
const ccUnreadCount = ref<number | undefined>(undefined)

const statusTabs = computed<StatusTabItem[]>(() => [
  { value: 'todo', labelKey: 'approval.approval.tabTodo', count: todoCount.value },
  { value: 'initiated', labelKey: 'approval.approval.tabInitiated' },
  { value: 'cc', labelKey: 'approval.approval.tabCc', count: ccUnreadCount.value },
  { value: 'done', labelKey: 'approval.approval.tabDone' },
])

type Row = Record<string, unknown>

const list = useListPage<Row>({
  fetch: async (params) => {
    if (activeTab.value === 'cc') {
      const data = await listCcItems({
        ...params,
        status: undefined,
        unread: ccUnreadOnly.value ? 1 : 0,
      })
      return { items: data.items as unknown as Row[], total: data.total ?? 0 }
    }
    const data = await listApprovalTasks(activeTab.value as ApprovalTab, {
      ...params,
      status: undefined,
      q: searchModel.value.q || undefined,
    })
    return { items: data.items as unknown as Row[], total: data.total ?? 0 }
  },
  defaultStatus: 'todo',
  autoLoad: false,
})

const ccUnreadOnly = ref(false)

const baseColumns: ListColumn[] = [
  { prop: 'title', labelKey: 'approval.approval.titleField', minWidth: 220, fixed: 'left' },
  { prop: 'bizType', labelKey: 'approval.approval.bizType', width: 100 },
  { prop: 'nodeName', labelKey: 'approval.approval.nodeName', width: 120 },
  { prop: 'status', labelKey: 'approval.approval.status', width: 100 },
  { prop: 'initiatorName', labelKey: 'approval.approval.initiatorName', width: 110 },
  { prop: 'assigneeName', labelKey: 'approval.approval.assigneeName', width: 110 },
  { prop: 'createTime', labelKey: 'approval.approval.createTime', width: 160 },
  { prop: 'actedAt', labelKey: 'approval.approval.actedAt', width: 160 },
]

const ccColumns: ListColumn[] = [
  { prop: 'title', labelKey: 'approval.approval.titleField', minWidth: 220, fixed: 'left' },
  { prop: 'bizType', labelKey: 'approval.approval.bizType', width: 100 },
  { prop: 'nodeName', labelKey: 'approval.approval.nodeName', width: 120 },
  { prop: 'instanceStatus', labelKey: 'approval.approval.instanceStatus', width: 100 },
  { prop: 'initiatorName', labelKey: 'approval.approval.initiatorName', width: 110 },
  { prop: 'readAt', labelKey: 'approval.approval.readAt', width: 160 },
  { prop: 'createTime', labelKey: 'approval.approval.createTime', width: 160 },
]

const columns = computed<ListColumn[]>(() => (activeTab.value === 'cc' ? ccColumns : baseColumns))

async function refreshTabCounts() {
  try {
    const todo = await listApprovalTasks('todo', { page: 1, size: 1 })
    todoCount.value = todo.total ?? 0
  } catch {
    todoCount.value = undefined
  }
  try {
    const cc = await listCcItems({ page: 1, size: 1, unread: 1 })
    ccUnreadCount.value = cc.total ?? 0
  } catch {
    ccUnreadCount.value = undefined
  }
}

function switchTab(tab: string) {
  activeTab.value = tab as CenterTab
  list.query.page = 1
  list.refresh()
}

function toggleUnreadOnly(v: boolean) {
  ccUnreadOnly.value = v
  list.query.page = 1
  list.refresh()
}

// --- 实例详情抽屉 ---

const drawerVisible = ref(false)
const current = ref<Row | null>(null)
const detail = ref<ApprovalInstanceDetail | null>(null)
const records = ref<TimelineRecord[]>([])
const detailLoading = ref(false)

async function openDetail(row: Row) {
  current.value = row
  detail.value = null
  records.value = []
  drawerVisible.value = true
  detailLoading.value = true
  try {
    const inst = await getInstance(Number(row.instanceId))
    detail.value = inst
    records.value = inst.timeline ?? []
  } catch {
    try {
      const tl = await getTimeline(String(row.bizType), Number(row.bizId))
      records.value = tl.records ?? []
    } catch {
      records.value = []
    }
  } finally {
    detailLoading.value = false
  }
  // 抄送条目打开即标记已读
  if (activeTab.value === 'cc' && row.id && !row.readAt) {
    try {
      await markCcRead(Number(row.id))
      row.readAt = '1'
      void refreshTabCounts()
    } catch {
      /* http notifies */
    }
  }
}

/** 快照字段名 → i18n 标签：先查各模块既有键，未命中再机械转可读英文 */
const SNAPSHOT_LABEL_PREFIXES = [
  'approval.approval.snapshotField',
  'contract.contract',
  'task.task',
  'report.report',
  'finance.settlement',
]

function snapshotLabel(key: string) {
  for (const prefix of SNAPSHOT_LABEL_PREFIXES) {
    const tk = `${prefix}.${key}`
    const tr = t(tk)
    if (typeof tr === 'string' && tr !== tk) return tr
  }
  const words = key
    .replace(/_/g, ' ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .trim()
  return words.charAt(0).toUpperCase() + words.slice(1)
}

function snapshotValue(v: unknown, key = ''): string {
  if (v === null || v === undefined || v === '') return '-'
  if (typeof v === 'object') return JSON.stringify(v, null, 2)
  const s = String(v)
  if (/status/i.test(key) && /^[a-z_]+$/.test(s)) {
    for (const tk of [`report.report.status.${s}`, `common.status.${s}`]) {
      const tr = t(tk)
      if (typeof tr === 'string' && tr !== tk) return tr
    }
  }
  return s
}

function onDone() {
  drawerVisible.value = false
  list.refresh()
  void refreshTabCounts()
}

function bizTypeLabel(bt: string) {
  if (bt === 'contract') return t('approval.approval.bizContract')
  if (bt === 'task') return t('approval.approval.bizTask')
  if (bt === 'report') return t('approval.approval.bizReport')
  if (bt === 'invoice') return t('approval.approval.bizInvoice')
  return bt
}

const canAct = computed(() => activeTab.value === 'todo' && current.value?.status === 'pending')
const canWithdraw = computed(() => activeTab.value === 'initiated' && current.value?.status === 'running')

onMounted(() => {
  list.refresh()
  void refreshTabCounts()
})
</script>

<template>
  <ListPage :title="t('approval.approval.title')" :loading="list.loading.value">
    <template #actions>
      <el-switch
        v-if="activeTab === 'cc'"
        :model-value="ccUnreadOnly"
        :active-text="t('approval.approval.unreadOnly')"
        @update:model-value="toggleUnreadOnly(Boolean($event))"
      />
      <ExportButton
        v-if="activeTab !== 'cc'"
        v-permission="'approval:view'"
        :export-fn="() => exportApprovalTasks(activeTab as ApprovalTab)"
      />
      <el-button @click="list.refresh(); refreshTabCounts()">{{ t('common.action.refresh') }}</el-button>
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
        :model-value="activeTab"
        @update:model-value="switchTab"
      />
    </template>

    <template #table>
      <ListTable
        :columns="columns"
        :data="list.items.value"
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
        <template #instanceStatus="{ row }">
          <StatusTag :status="String(row.instanceStatus)" i18n-prefix="approval.approval.status" />
        </template>
        <template #title="{ row }">
          <el-button link type="primary" @click="openDetail(row)">{{ row.title }}</el-button>
          <el-badge
            v-if="activeTab === 'initiated' && Number(row.unreadCount) > 0"
            :value="Number(row.unreadCount)"
            :max="99"
            class="unread-badge"
          />
          <el-tag v-if="activeTab === 'cc' && !row.readAt" type="danger" size="small" effect="plain">
            {{ t('approval.approval.ccUnread') }}
          </el-tag>
        </template>
        <template #readAt="{ row }">
          {{ row.readAt ? row.readAt : t('approval.approval.ccUnread') }}
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="110" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openDetail(row)">
                {{ t('common.action.detail') }}
              </el-button>
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-drawer v-model="drawerVisible" :title="t('approval.approval.detail')" size="560px">
    <div v-if="current" class="drawer-body" v-loading="detailLoading">
      <el-descriptions :column="1" border>
        <el-descriptions-item :label="t('approval.approval.titleField')">{{ current.title }}</el-descriptions-item>
        <el-descriptions-item :label="t('approval.approval.bizType')">
          {{ bizTypeLabel(String(current.bizType)) }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('approval.approval.nodeName')">{{ current.nodeName }}</el-descriptions-item>
        <el-descriptions-item :label="t('approval.approval.initiatorName')">{{ current.initiatorName }}</el-descriptions-item>
        <el-descriptions-item :label="t('approval.approval.comment')">{{ current.comment || '-' }}</el-descriptions-item>
      </el-descriptions>

      <template v-if="detail?.processGraph?.nodes?.length">
        <div class="section-title">{{ t('approval.approval.flowGraph') }}</div>
        <FlowGraphViewer :graph="detail.processGraph" :current-seqs="detail.currentNodeIds ?? []" />
      </template>

      <div class="section-title">{{ t('approval.approval.timeline') }}</div>
      <ApprovalTimeline :records="records" :loading="detailLoading" />

      <template v-if="detail?.snapshot && Object.keys(detail.snapshot).length">
        <div class="section-title">{{ t('approval.approval.formSnapshot') }}</div>
        <el-descriptions :column="1" border>
          <el-descriptions-item v-for="(v, k) in detail.snapshot" :key="k" :label="snapshotLabel(String(k))">
            <pre v-if="typeof v === 'object' && v !== null" class="snapshot-json">{{ snapshotValue(v, String(k)) }}</pre>
            <template v-else>{{ snapshotValue(v, String(k)) }}</template>
          </el-descriptions-item>
        </el-descriptions>
      </template>

      <template v-if="canAct || canWithdraw">
        <div class="section-title">{{ t('common.action.operate') }}</div>
        <ApprovalActionbar
          :task="current as unknown as ApprovalTask"
          :can-act="canAct"
          :can-withdraw="canWithdraw"
          @done="onDone"
        />
      </template>
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

.unread-badge {
  margin-left: var(--bs-space-2);
  vertical-align: super;
}
</style>
