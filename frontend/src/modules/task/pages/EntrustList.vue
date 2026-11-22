<script setup lang="ts">
/** 在线任务委托受理台（B2）：客户自助下单与业务代提交的委托单受理、派发任务与跟踪。 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElMessage, ElMessageBox } from 'element-plus'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ContractSelect from '@/components/form/ContractSelect.vue'
import { useListPage } from '@/composables/useListPage'
import { useDictOptions } from '@/composables/useDict'
import {
  cancelEntrust,
  createEntrust,
  dispatchEntrust,
  entrustCounts,
  exportEntrusts,
  getEntrust,
  listEntrusts,
  reviewEntrust,
} from '@/api/entrust'
import type { TaskEntrust } from '@/api/types'

defineOptions({ name: 'EntrustList' })

/** 创建弹窗里的试验项目编辑行（提交时转成后端 snake_case 字段） */
interface EntrustItemForm {
  itemCode: string
  name: string
  std: string
  qty: number
  needReport: boolean
  reportType: string
  remark: string
}

const { t } = useI18n()
const typeOpts = useDictOptions('entrust_type')

const searchModel = ref<Record<string, any>>({ q: '', entrust_type: '', source: '' })
const searchFields = computed<SearchField[]>(() => [
  {
    key: 'q',
    labelKey: 'task.entrust.searchName',
    placeholderKey: 'task.entrust.placeholderName',
    width: 240,
  },
  {
    key: 'entrust_type',
    labelKey: 'task.entrust.entrustType',
    type: 'select',
    options: typeOpts.opts.value,
    width: 160,
  },
  {
    key: 'source',
    labelKey: 'task.entrust.source',
    type: 'select',
    options: [
      { label: t('task.entrust.sourcePortal'), value: 'portal' },
      { label: t('task.entrust.sourceStaff'), value: 'staff' },
    ],
    width: 160,
  },
])

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'submitted', labelKey: 'task.entrust.statusSubmitted', count: 0 },
  { value: 'accepted', labelKey: 'task.entrust.statusAccepted', count: 0 },
  { value: 'dispatched', labelKey: 'task.entrust.statusDispatched', count: 0 },
  { value: 'closed', labelKey: 'task.entrust.statusClosed', count: 0 },
  { value: 'rejected', labelKey: 'task.entrust.statusRejected', count: 0 },
  { value: 'cancelled', labelKey: 'task.entrust.statusCancelled', count: 0 },
])

const counts = ref<Record<string, number>>({})

async function loadCounts() {
  try {
    counts.value = (await entrustCounts()) ?? {}
    let all = 0
    for (const tab of statusTabs.value) {
      if (tab.value === 'all') continue
      tab.count = counts.value[tab.value] ?? 0
      all += tab.count
    }
    const allTab = statusTabs.value.find((x) => x.value === 'all')
    if (allTab) allTab.count = all
  } catch {
    /* counts optional */
  }
}

onMounted(() => void loadCounts())

const list = useListPage<TaskEntrust>({
  fetch: async (params) => {
    const data = await listEntrusts({
      ...params,
      q: searchModel.value.q || undefined,
      filters: {
        ...((params.filters as Record<string, unknown>) || {}),
        entrust_type: searchModel.value.entrust_type || undefined,
        source: searchModel.value.source || undefined,
      },
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportEntrusts({
      ...params,
      q: searchModel.value.q || undefined,
      filters: {
        ...((params.filters as Record<string, unknown>) || {}),
        entrust_type: searchModel.value.entrust_type || undefined,
        source: searchModel.value.source || undefined,
      },
    }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const typeOptions = computed(() => typeOpts.opts.value)

const columns: ListColumn[] = [
  { prop: 'entrustNo', labelKey: 'task.entrust.entrustNo', width: 150, fixed: 'left', sortable: 'entrust_no' },
  { prop: 'title', labelKey: 'task.entrust.titleLabel', minWidth: 200, fixed: 'left', sortable: 'title' },
  { prop: 'entrustType', labelKey: 'task.entrust.entrustType', width: 120, sortable: 'entrust_type' },
  { prop: 'customerName', labelKey: 'task.entrust.customerName', minWidth: 150, sortable: 'customer_name' },
  { prop: 'contractNo', labelKey: 'task.entrust.contractNo', width: 150 },
  { prop: 'source', labelKey: 'task.entrust.source', width: 110 },
  { prop: 'applicantName', labelKey: 'task.entrust.applicantName', width: 110 },
  { prop: 'handlerName', labelKey: 'task.entrust.handlerName', width: 110 },
  { prop: 'planEndDate', labelKey: 'task.entrust.planEndDate', width: 120, sortable: 'plan_end_date' },
  { prop: 'status', labelKey: 'task.entrust.status', width: 110, sortable: 'status' },
  { prop: 'createTime', labelKey: 'task.entrust.createTime', width: 160, sortable: 'create_time' },
]

function rowActions(row: TaskEntrust): ActionItem[] {
  const s = String(row.status)
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  if (s === 'submitted') {
    acts.push({ key: 'accept', tip: 'task.entrust.accept', perm: 'task:entrust:review' })
    acts.push({ key: 'reject', tip: 'task.entrust.reject', perm: 'task:entrust:review' })
  }
  if (s === 'accepted') acts.push({ key: 'dispatch', tip: 'task.entrust.dispatch', perm: 'task:entrust:dispatch' })
  if (['draft', 'submitted', 'accepted'].includes(s)) {
    acts.push({ key: 'cancel', tip: 'task.entrust.cancel', icon: 'Close', danger: true, perm: 'task:entrust:review' })
  }
  return acts
}

/* ---------------- 详情抽屉 ---------------- */
const detailVisible = ref(false)
const detail = ref<TaskEntrust | null>(null)

async function openDetail(row: TaskEntrust) {
  try {
    detail.value = await getEntrust(row.id)
    detailVisible.value = true
  } catch {
    /* http notifies */
  }
}

/* ---------------- 受理 / 驳回 ---------------- */
const reviewVisible = ref(false)
const reviewTarget = ref<TaskEntrust | null>(null)
const reviewForm = ref<{ action: 'accept' | 'reject'; comment: string; bizOwnerName: string }>({
  action: 'accept',
  comment: '',
  bizOwnerName: '',
})

function openReview(row: TaskEntrust, action: 'accept' | 'reject') {
  reviewTarget.value = row
  reviewForm.value = { action, comment: '', bizOwnerName: row.bizOwnerName || '' }
  reviewVisible.value = true
}

async function submitReview() {
  const target = reviewTarget.value
  if (!target) return
  try {
    await reviewEntrust(target.id, {
      action: reviewForm.value.action,
      comment: reviewForm.value.comment,
      bizOwnerName: reviewForm.value.bizOwnerName || undefined,
    })
    ElMessage.success(t('common.message.submitSuccess'))
    reviewVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------------- 派发任务 ---------------- */
const dispatchVisible = ref(false)
const dispatchTarget = ref<TaskEntrust | null>(null)
const dispatchForm = ref<{ ownerName: string; deptName: string; planFinishDate: string; comment: string }>({
  ownerName: '',
  deptName: '',
  planFinishDate: '',
  comment: '',
})

function openDispatch(row: TaskEntrust) {
  dispatchTarget.value = row
  dispatchForm.value = {
    ownerName: row.handlerName || '',
    deptName: '',
    planFinishDate: row.planEndDate || '',
    comment: '',
  }
  dispatchVisible.value = true
}

async function submitDispatch() {
  const target = dispatchTarget.value
  if (!target) return
  try {
    await dispatchEntrust(target.id, {
      ownerName: dispatchForm.value.ownerName,
      deptName: dispatchForm.value.deptName,
      planFinishDate: dispatchForm.value.planFinishDate || null,
      comment: dispatchForm.value.comment,
    })
    ElMessage.success(t('task.entrust.dispatchSuccess'))
    dispatchVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------------- 业务代提交 ---------------- */
const createVisible = ref(false)
const createForm = ref<{
  title: string
  entrust_type: string
  contract_id: number | null
  requirement: string
  sample_desc: string
  plan_start_date: string
  plan_end_date: string
  priority: string
  amount: number | null
  remark: string
  items: EntrustItemForm[]
}>({
  title: '',
  entrust_type: 'test',
  contract_id: null,
  requirement: '',
  sample_desc: '',
  plan_start_date: '',
  plan_end_date: '',
  priority: 'normal',
  amount: null,
  remark: '',
  items: [],
})

function openCreate() {
  createForm.value = {
    title: '',
    entrust_type: 'test',
    contract_id: null,
    requirement: '',
    sample_desc: '',
    plan_start_date: '',
    plan_end_date: '',
    priority: 'normal',
    amount: null,
    remark: '',
    items: [
      { itemCode: '01', name: '', std: '', qty: 1, needReport: true, reportType: '', remark: '' },
    ],
  }
  createVisible.value = true
}

function addItem() {
  createForm.value.items.push({
    itemCode: String(createForm.value.items.length + 1).padStart(2, '0'),
    name: '',
    std: '',
    qty: 1,
    needReport: true,
    reportType: '',
    remark: '',
  })
}

function removeItem(index: number) {
  createForm.value.items.splice(index, 1)
}

async function submitCreate() {
  const f = createForm.value
  if (!f.title.trim()) {
    ElMessage.warning(t('common.form.required'))
    return
  }
  if (!f.contract_id) {
    ElMessage.warning(t('task.entrust.contractRequired'))
    return
  }
  try {
    await createEntrust({
      ...f,
      items: f.items.map((i, idx) => ({
        item_code: i.itemCode || String(idx + 1).padStart(2, '0'),
        name: i.name,
        std: i.std,
        qty: i.qty,
        need_report: i.needReport ? 1 : 0,
        report_type: i.reportType,
        remark: i.remark,
      })),
    })
    ElMessage.success(t('common.message.submitSuccess'))
    createVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doCancel(row: TaskEntrust) {
  try {
    await ElMessageBox.confirm(t('task.entrust.cancelConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await cancelEntrust(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

function onRowAction(key: string, row: TaskEntrust) {
  if (key === 'detail') void openDetail(row)
  else if (key === 'accept') openReview(row, 'accept')
  else if (key === 'reject') openReview(row, 'reject')
  else if (key === 'dispatch') openDispatch(row)
  else if (key === 'cancel') void doCancel(row)
}
</script>

<template>
  <ListPage :title="t('task.entrust.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'task:entrust:create'" type="primary" @click="openCreate">
        {{ t('task.entrust.create') }}
      </el-button>
      <ExportButton v-permission="'task:entrust:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '', entrust_type: '', source: '' }; list.reset()"
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
        @sort-change="list.onSortChange"
      >
        <template #entrustType="{ row }">
          {{ typeOptions.find((x) => x.value === row.entrustType)?.label || row.entrustType || '-' }}
        </template>
        <template #source="{ row }">
          {{ row.source === 'portal' ? t('task.entrust.sourcePortal') : t('task.entrust.sourceStaff') }}
        </template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="task.entrust.status" />
        </template>
        <template #entrustNo="{ row }">
          <el-button link type="primary" @click="openDetail(row as unknown as TaskEntrust)">
            {{ row.entrustNo || '-' }}
          </el-button>
        </template>
        <template #extraColumns>
          <el-table-column
            :label="t('common.action.operate')"
            width="130"
            fixed="right"
            align="center"
            header-align="center"
          >
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as TaskEntrust)"
                @select="(k) => onRowAction(k, row as unknown as TaskEntrust)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <!-- 详情 -->
  <el-drawer v-model="detailVisible" :size="'var(--bs-layout-drawer-lg)'" :title="t('task.entrust.detail')">
    <el-descriptions v-if="detail" :column="2" border>
      <el-descriptions-item :label="t('task.entrust.entrustNo')">{{ detail.entrustNo || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('task.entrust.status')">
        <StatusTag :status="detail.status" i18n-prefix="task.entrust.status" />
      </el-descriptions-item>
      <el-descriptions-item :label="t('task.entrust.titleLabel')" :span="2">{{ detail.title }}</el-descriptions-item>
      <el-descriptions-item :label="t('task.entrust.entrustType')">
        {{ detail.entrustTypeLabel || detail.entrustType || '-' }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('task.entrust.priority')">
        {{ detail.priority === 'urgent' ? t('task.entrust.priorityUrgent') : t('task.entrust.priorityNormal') }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('task.entrust.customerName')">{{ detail.customerName || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('task.entrust.contractNo')">{{ detail.contractNo || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('task.entrust.applicantName')">{{ detail.applicantName || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('task.entrust.applicantPhone')">{{ detail.applicantPhone || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('task.entrust.source')">
        {{ detail.source === 'portal' ? t('task.entrust.sourcePortal') : t('task.entrust.sourceStaff') }}
      </el-descriptions-item>
      <el-descriptions-item :label="t('task.entrust.handlerName')">{{ detail.handlerName || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('task.entrust.bizOwnerName')">{{ detail.bizOwnerName || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('task.entrust.planStartDate')">{{ detail.planStartDate || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('task.entrust.planEndDate')">{{ detail.planEndDate || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('task.entrust.sampleDesc')" :span="2">{{ detail.sampleDesc || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('task.entrust.requirement')" :span="2">{{ detail.requirement || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('task.entrust.taskNo')">{{ detail.taskNo || '-' }}</el-descriptions-item>
      <el-descriptions-item :label="t('task.entrust.reviewComment')">{{ detail.reviewComment || '-' }}</el-descriptions-item>
    </el-descriptions>

    <h4 class="drawer-sub-title">{{ t('task.entrust.items') }}</h4>
    <el-table v-if="detail?.items?.length" :data="detail.items" border size="small">
      <el-table-column :label="t('task.entrust.itemCode')" prop="itemCode" width="80" />
      <el-table-column :label="t('task.entrust.itemName')" prop="name" min-width="160" />
      <el-table-column :label="t('task.entrust.itemStd')" prop="std" min-width="140" />
      <el-table-column :label="t('task.entrust.itemQty')" prop="qty" width="80" align="center" />
      <el-table-column :label="t('task.entrust.needReport')" width="90" align="center">
        <template #default="{ row }">{{ row.needReport ? t('common.action.yes') : t('common.action.no') }}</template>
      </el-table-column>
    </el-table>
    <el-empty v-else :description="t('common.table.empty')" :image-size="60" />
  </el-drawer>

  <!-- 受理 / 驳回 -->
  <el-dialog v-model="reviewVisible" :width="'var(--bs-layout-dialog-sm)'" :title="t('task.entrust.reviewTitle')">
    <el-form label-position="top">
      <el-form-item :label="t('task.entrust.comment')">
        <el-input v-model="reviewForm.comment" type="textarea" :rows="3" :maxlength="500" show-word-limit />
      </el-form-item>
      <el-form-item v-if="reviewForm.action === 'accept'" :label="t('task.entrust.bizOwnerName')">
        <el-input v-model="reviewForm.bizOwnerName" :maxlength="64" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="reviewVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="submitReview">{{ t('common.action.confirm') }}</el-button>
    </template>
  </el-dialog>

  <!-- 派发任务 -->
  <el-dialog v-model="dispatchVisible" :width="'var(--bs-layout-dialog-sm)'" :title="t('task.entrust.dispatchTitle')">
    <el-form label-position="top">
      <el-form-item :label="t('task.entrust.ownerName')">
        <el-input v-model="dispatchForm.ownerName" :maxlength="64" />
      </el-form-item>
      <el-form-item :label="t('task.entrust.deptName')">
        <el-input v-model="dispatchForm.deptName" :maxlength="64" />
      </el-form-item>
      <el-form-item :label="t('task.entrust.planFinishDate')">
        <el-date-picker v-model="dispatchForm.planFinishDate" type="date" value-format="YYYY-MM-DD" />
      </el-form-item>
      <el-form-item :label="t('task.entrust.comment')">
        <el-input v-model="dispatchForm.comment" type="textarea" :rows="2" :maxlength="500" show-word-limit />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dispatchVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="submitDispatch">{{ t('common.action.confirm') }}</el-button>
    </template>
  </el-dialog>

  <!-- 业务代提交 -->
  <el-dialog v-model="createVisible" :width="'var(--bs-layout-dialog-lg)'" :title="t('task.entrust.createTitle')">
    <el-form label-position="top">
      <el-form-item :label="t('task.entrust.titleLabel')" required>
        <el-input v-model="createForm.title" :maxlength="255" />
      </el-form-item>
      <el-form-item :label="t('task.entrust.entrustType')">
        <el-select v-model="createForm.entrust_type" style="width: 100%">
          <el-option v-for="o in typeOptions" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('task.entrust.contractNo')" required>
        <ContractSelect v-model="createForm.contract_id" :placeholder="t('task.entrust.contractPlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('task.entrust.sampleDesc')">
        <el-input v-model="createForm.sample_desc" :maxlength="500" />
      </el-form-item>
      <el-form-item :label="t('task.entrust.requirement')">
        <el-input v-model="createForm.requirement" type="textarea" :rows="3" :maxlength="4000" show-word-limit />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('task.entrust.planStartDate')">
            <el-date-picker v-model="createForm.plan_start_date" type="date" value-format="YYYY-MM-DD" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('task.entrust.planEndDate')">
            <el-date-picker v-model="createForm.plan_end_date" type="date" value-format="YYYY-MM-DD" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item :label="t('task.entrust.priority')">
        <el-radio-group v-model="createForm.priority">
          <el-radio value="normal">{{ t('task.entrust.priorityNormal') }}</el-radio>
          <el-radio value="urgent">{{ t('task.entrust.priorityUrgent') }}</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item :label="t('task.entrust.items')">
        <div class="item-editor">
          <div v-for="(item, idx) in createForm.items" :key="idx" class="item-row">
            <el-input v-model="item.itemCode" :placeholder="t('task.entrust.itemCode')" class="item-code" />
            <el-input v-model="item.name" :placeholder="t('task.entrust.itemName')" class="item-name" />
            <el-input v-model="item.std" :placeholder="t('task.entrust.itemStd')" class="item-std" />
            <el-input-number v-model="item.qty" :min="0" :controls="false" class="item-qty" />
            <el-checkbox v-model="item.needReport" :label="t('task.entrust.needReport')" />
            <el-button link type="danger" @click="removeItem(idx)">
              {{ t('common.action.delete') }}
            </el-button>
          </div>
          <el-button size="small" @click="addItem">{{ t('task.entrust.addItem') }}</el-button>
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="createVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="submitCreate">{{ t('task.entrust.submit') }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.drawer-sub-title {
  margin: var(--bs-space-4) 0 var(--bs-space-2);
  font-size: var(--bs-typography-font-size-md);
  color: var(--bs-color-fg-default);
}

.item-editor {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  width: 100%;
}

.item-row {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.item-code {
  width: 80px;
}

.item-name {
  flex: 1;
}

.item-std {
  flex: 1;
}

.item-qty {
  width: 90px;
}
</style>
