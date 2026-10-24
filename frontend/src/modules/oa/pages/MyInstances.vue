<script setup lang="ts">
/** OA 我的申请：列表（状态筛选/分页）+ 详情抽屉（表单只读回显 + 流程图 + 时间线 + 撤回）。 */
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ApprovalTimeline from '@/components/approval/ApprovalTimeline.vue'
import FlowGraphViewer from '@/components/flow/FlowGraphViewer.vue'
import FormRenderer from '@/modules/oa/components/FormRenderer.vue'
import { useListPage } from '@/composables/useListPage'
import { exportMyOaInstances, getOaInstance, listMyOaInstances, withdrawOaInstance } from '@/api/oa'
import { getInstance } from '@/api/approval'
import { useDict } from '@/composables/useDict'
import type { FlowGraphData, OaInstanceDetail, OaInstanceItem } from '@/api/types'

defineOptions({ name: 'MyInstances' })

const { t } = useI18n()
const { options: dictOptions } = useDict()

const activeStatus = ref('all')
const statusTabs = computed<StatusTabItem[]>(() => [
  { value: 'all', labelKey: 'common.action.all' },
  { value: 'running', label: t('oa.status.running') },
  { value: 'approved', label: t('oa.status.approved') },
  { value: 'rejected', label: t('oa.status.rejected') },
  { value: 'withdrawn', label: t('oa.status.withdrawn') },
  { value: 'terminated', label: t('oa.status.terminated') },
])

const list = useListPage<OaInstanceItem>({
  fetch: async (params) => {
    const data = await listMyOaInstances({
      ...params,
      status: activeStatus.value === 'all' ? '' : activeStatus.value,
    })
    return { items: data.items, total: data.total ?? 0 }
  },
  defaultStatus: 'all',
})

const columns: ListColumn[] = [
  { prop: 'displayNo', labelKey: 'oa.my.displayNo', width: 150, fixed: 'left', sortable: 'display_no' },
  { prop: 'formName', labelKey: 'oa.my.formName', minWidth: 130, sortable: 'form_name' },
  { prop: 'category', labelKey: 'oa.design.category', width: 90, sortable: 'category' },
  { prop: 'status', labelKey: 'oa.my.status', width: 100, sortable: 'status' },
  { prop: 'pendingNames', labelKey: 'oa.my.pendingNames', minWidth: 120 },
  { prop: 'createTime', labelKey: 'oa.my.createTime', width: 165, sortable: 'create_time' },
  { prop: 'finishedAt', labelKey: 'oa.my.finishedAt', width: 165, sortable: 'finished_at' },
]

function switchStatus(v: string) {
  activeStatus.value = v
  list.query.page = 1
  list.refresh()
}

const categoryLabels = ref<Record<string, string>>({})
onMounted(async () => {
  const opts = await dictOptions('oa_category')
  categoryLabels.value = Object.fromEntries(opts.map((o) => [o.value, o.label]))
})

function categoryLabel(c: string) {
  return categoryLabels.value[c] || c || '-'
}

/* ---------- 详情抽屉 ---------- */
const drawerVisible = ref(false)
const detail = ref<OaInstanceDetail | null>(null)
const processGraph = ref<FlowGraphData | null>(null)
const currentSeqs = ref<number[]>([])
const detailLoading = ref(false)

async function openDetail(row: OaInstanceItem) {
  detail.value = null
  processGraph.value = null
  currentSeqs.value = []
  drawerVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getOaInstance(row.id)
    if (detail.value.flowInstanceId) {
      try {
        const inst = await getInstance(detail.value.flowInstanceId)
        processGraph.value = inst.processGraph ?? null
        currentSeqs.value = inst.currentNodeIds ?? []
      } catch {
        processGraph.value = null
      }
    }
  } catch {
    /* http notifies */
  } finally {
    detailLoading.value = false
  }
}

const canWithdraw = computed(() => detail.value?.status === 'running')

async function doWithdraw() {
  if (!detail.value) return
  try {
    await ElMessageBox.confirm(t('oa.my.withdrawConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await withdrawOaInstance(detail.value.id)
    ElMessage.success(t('oa.my.withdrawDone'))
    drawerVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  }
}
</script>

<template>
  <ListPage :title="t('oa.my.title')" :loading="list.loading.value">
    <template #actions>
      <ExportButton
        v-permission="'oa:my'"
        :export-fn="() => exportMyOaInstances({ status: activeStatus === 'all' ? '' : activeStatus })"
      />
      <el-button @click="list.refresh()">{{ t('common.action.refresh') }}</el-button>
    </template>

    <template #statusTabs>
      <StatusTabs :tabs="statusTabs" :model-value="activeStatus" @update:model-value="switchStatus" />
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
        @sort-change="list.onSortChange"
      >
        <template #displayNo="{ row }">
          <el-button link type="primary" @click="openDetail(row as OaInstanceItem)">{{ row.displayNo }}</el-button>
        </template>
        <template #category="{ row }">{{ categoryLabel(String(row.category)) }}</template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="oa.status" />
        </template>
        <template #pendingNames="{ row }">{{ row.pendingNames || '-' }}</template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="90" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar :actions="[{ key: 'detail', tip: 'common.action.detail' }]" @select="openDetail(row as OaInstanceItem)" />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-drawer v-model="drawerVisible" :title="detail ? `${detail.displayNo} ${detail.formName}` : ''" size="620px">
    <div v-if="detail" class="drawer-body" v-loading="detailLoading">
      <el-descriptions :column="2" border>
        <el-descriptions-item :label="t('oa.my.displayNo')">{{ detail.displayNo }}</el-descriptions-item>
        <el-descriptions-item :label="t('oa.my.status')">
          <StatusTag :status="detail.status" i18n-prefix="oa.status" />
        </el-descriptions-item>
        <el-descriptions-item :label="t('oa.my.createTime')">{{ detail.createTime }}</el-descriptions-item>
        <el-descriptions-item :label="t('oa.my.pendingNames')">{{ detail.pendingNames || '-' }}</el-descriptions-item>
      </el-descriptions>

      <div class="section-title">{{ t('oa.my.formData') }}</div>
      <FormRenderer :fields="detail.schema?.fields ?? []" :model-value="detail.formData" disabled />

      <template v-if="processGraph?.nodes?.length">
        <div class="section-title">{{ t('approval.approval.flowGraph') }}</div>
        <FlowGraphViewer :graph="processGraph" :current-seqs="currentSeqs" />
      </template>

      <div class="section-title">{{ t('approval.approval.timeline') }}</div>
      <ApprovalTimeline :records="detail.timeline" :loading="detailLoading" />

      <div v-if="canWithdraw" class="drawer-actions">
        <el-button type="warning" @click="doWithdraw">{{ t('oa.my.withdraw') }}</el-button>
      </div>
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

.drawer-actions {
  display: flex;
  justify-content: flex-end;
}
</style>
