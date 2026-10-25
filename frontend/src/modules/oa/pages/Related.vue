<script setup lang="ts">
/** OA 与我相关：待办 / 已办 / 抄送（复用通用审批待办端点，biz_type=oa 过滤）。
 * 详情抽屉：表单只读回显 + 流程图 + 时间线；待办可审批操作（同意/驳回/转办/加签）。
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar from '@/components/list/ActionBar.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ApprovalTimeline from '@/components/approval/ApprovalTimeline.vue'
import ApprovalActionbar from '@/components/approval/ApprovalActionbar.vue'
import FlowGraphViewer from '@/components/flow/FlowGraphViewer.vue'
import FormRenderer from '@/modules/oa/components/FormRenderer.vue'
import { useListPage } from '@/composables/useListPage'
import { getOaInstance, listOaRelated, oaRelatedCounts } from '@/api/oa'
import { getInstance, markCcRead } from '@/api/approval'
import type { ApprovalInstanceDetail, ApprovalTask, OaInstanceDetail } from '@/api/types'

defineOptions({ name: 'Related' })

type RelTab = 'todo' | 'done' | 'cc'
type Row = Record<string, unknown>

const { t } = useI18n()

const activeTab = ref<RelTab>('todo')
const counts = ref<Record<string, number>>({})
const statusTabs = computed<StatusTabItem[]>(() => [
  { value: 'todo', label: t('oa.related.tabTodo'), count: counts.value.todo ?? 0 },
  { value: 'done', label: t('oa.related.tabDone'), count: counts.value.done ?? 0 },
  { value: 'cc', label: t('oa.related.tabCc'), count: counts.value.cc ?? 0 },
])

async function loadCounts() {
  try {
    counts.value = (await oaRelatedCounts()) ?? {}
  } catch {
    /* counts optional */
  }
}

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'oa.related.searchQ', placeholderKey: 'oa.related.placeholderQ', width: 240 },
]

const list = useListPage<Row>({
  fetch: async (params) => {
    const data = await listOaRelated(activeTab.value, {
      ...params,
      status: undefined,
      q: searchModel.value.q || undefined,
    })
    return { items: data.items as Row[], total: data.total ?? 0 }
  },
  defaultStatus: 'todo',
  autoLoad: false,
  onLoaded: () => {
    void loadCounts()
  },
})

const baseColumns: ListColumn[] = [
  { prop: 'title', labelKey: 'approval.approval.titleField', minWidth: 200, fixed: 'left' },
  { prop: 'nodeName', labelKey: 'approval.approval.nodeName', width: 130 },
  { prop: 'status', labelKey: 'approval.approval.status', width: 100 },
  { prop: 'initiatorName', labelKey: 'approval.approval.initiatorName', width: 110 },
  { prop: 'createTime', labelKey: 'approval.approval.createTime', width: 165, sortable: 'create_time' },
  { prop: 'actedAt', labelKey: 'approval.approval.actedAt', width: 165, sortable: 'at' },
]

const ccColumns: ListColumn[] = [
  { prop: 'title', labelKey: 'approval.approval.titleField', minWidth: 200, fixed: 'left' },
  { prop: 'nodeName', labelKey: 'approval.approval.nodeName', width: 130 },
  { prop: 'instanceStatus', labelKey: 'approval.approval.instanceStatus', width: 100 },
  { prop: 'initiatorName', labelKey: 'approval.approval.initiatorName', width: 110 },
  { prop: 'readAt', labelKey: 'approval.approval.readAt', width: 165 },
  { prop: 'createTime', labelKey: 'approval.approval.createTime', width: 165, sortable: 'create_time' },
]

const columns = computed<ListColumn[]>(() => (activeTab.value === 'cc' ? ccColumns : baseColumns))

function switchTab(tab: string) {
  activeTab.value = tab as RelTab
  list.query.page = 1
  list.refresh()
}

/* ---------- 详情抽屉 ---------- */
const drawerVisible = ref(false)
const current = ref<Row | null>(null)
const oaDetail = ref<OaInstanceDetail | null>(null)
const flowDetail = ref<ApprovalInstanceDetail | null>(null)
const detailLoading = ref(false)

async function openDetail(row: Row) {
  current.value = row
  oaDetail.value = null
  flowDetail.value = null
  drawerVisible.value = true
  detailLoading.value = true
  try {
    // OA 单详情（bizId = oa_instance.id）：表单回显 + 时间线
    oaDetail.value = await getOaInstance(Number(row.bizId))
    if (oaDetail.value.flowInstanceId) {
      try {
        flowDetail.value = await getInstance(oaDetail.value.flowInstanceId)
      } catch {
        flowDetail.value = null
      }
    }
  } catch {
    /* http notifies */
  } finally {
    detailLoading.value = false
  }
  if (activeTab.value === 'cc' && row.id && !row.readAt) {
    try {
      await markCcRead(Number(row.id))
      row.readAt = '1'
    } catch {
      /* http notifies */
    }
  }
}

const canAct = computed(() => activeTab.value === 'todo' && current.value?.status === 'pending')

function onDone() {
  drawerVisible.value = false
  list.refresh()
}

onMounted(() => {
  void loadCounts()
  list.refresh()
})
</script>

<template>
  <ListPage :title="t('oa.related.title')" :loading="list.loading.value">
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
      <StatusTabs :tabs="statusTabs" :model-value="activeTab" @update:model-value="switchTab" />
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
        @sort-change="list.onSortChange"
      >
        <template #title="{ row }">
          <el-button link type="primary" @click="openDetail(row)">{{ row.title }}</el-button>
          <el-tag v-if="activeTab === 'cc' && !row.readAt" type="danger" size="small" effect="plain">
            {{ t('approval.approval.ccUnread') }}
          </el-tag>
        </template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="approval.approval.status" />
        </template>
        <template #instanceStatus="{ row }">
          <StatusTag :status="String(row.instanceStatus)" i18n-prefix="oa.status" />
        </template>
        <template #readAt="{ row }">
          {{ row.readAt ? row.readAt : t('approval.approval.ccUnread') }}
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="90" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar :actions="[{ key: 'detail', tip: 'common.action.detail' }]" @select="openDetail(row)" />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-drawer v-model="drawerVisible" :title="String(current?.title ?? '')" size="620px">
    <div v-if="current" class="drawer-body" v-loading="detailLoading">
      <el-descriptions :column="2" border>
        <el-descriptions-item :label="t('approval.approval.nodeName')">{{ current.nodeName }}</el-descriptions-item>
        <el-descriptions-item :label="t('approval.approval.initiatorName')">{{ current.initiatorName }}</el-descriptions-item>
      </el-descriptions>

      <template v-if="oaDetail">
        <div class="section-title">{{ t('oa.my.formData') }}</div>
        <FormRenderer :fields="oaDetail.schema?.fields ?? []" :model-value="oaDetail.formData" disabled />
      </template>

      <template v-if="flowDetail?.processGraph?.nodes?.length">
        <div class="section-title">{{ t('approval.approval.flowGraph') }}</div>
        <FlowGraphViewer :graph="flowDetail.processGraph as never" :current-seqs="flowDetail.currentNodeIds ?? []" />
      </template>

      <template v-if="oaDetail">
        <div class="section-title">{{ t('approval.approval.timeline') }}</div>
        <ApprovalTimeline :records="oaDetail.timeline" :loading="detailLoading" />
      </template>

      <template v-if="canAct">
        <div class="section-title">{{ t('common.action.operate') }}</div>
        <ApprovalActionbar :task="current as unknown as ApprovalTask" :can-act="canAct" @done="onDone" />
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
</style>
