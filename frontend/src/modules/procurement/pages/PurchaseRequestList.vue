<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import ApprovalTimeline from '@/components/approval/ApprovalTimeline.vue'
import { useListPage } from '@/composables/useListPage'
import { useDictOptions } from '@/composables/useDict'
import {
  listPurchaseRequests,
  purchaseRequestCounts,
  getPurchaseRequest,
  createPurchaseRequest,
  updatePurchaseRequest,
  deletePurchaseRequest,
  submitPurchaseRequest,
  voidPurchaseRequest,
  generateContract,
  exportPurchaseRequests,
} from '@/api/procurement'
import { listTasks } from '@/api/task'
import { customerOptions } from '@/api/crm'
import type {
  CustomerOption,
  PurchaseRequest,
  PurchaseRequestDetail,
  PurchaseRequestItem,
  Task,
} from '@/api/types'

defineOptions({ name: 'PurchaseRequestList' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const methodOpts = useDictOptions('purchase_method')

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'procurement.request.searchTitle', placeholderKey: 'procurement.request.placeholderTitle', width: 240 },
]

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'draft', labelKey: 'common.status.draft', count: 0 },
  { value: 'approving', labelKey: 'common.status.approving', count: 0 },
  { value: 'approved', labelKey: 'common.status.approved', count: 0 },
  { value: 'rejected', labelKey: 'common.status.rejected', count: 0 },
  { value: 'voided', labelKey: 'common.status.voided', count: 0 },
])

const counts = ref<Record<string, number>>({})

async function loadCounts() {
  try {
    counts.value = (await purchaseRequestCounts()) ?? {}
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

const list = useListPage<PurchaseRequest>({
  fetch: async (params) => {
    const data = await listPurchaseRequests({ ...params, q: searchModel.value.q || undefined })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) => exportPurchaseRequests({ ...params, q: searchModel.value.q || undefined }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'requestNo', labelKey: 'procurement.request.requestNo', width: 150, fixed: 'left', sortable: 'request_no' },
  { prop: 'title', labelKey: 'procurement.request.requestTitle', minWidth: 200, fixed: 'left', sortable: 'title' },
  { prop: 'taskNo', labelKey: 'procurement.request.task', width: 140 },
  { prop: 'purchaseMethod', labelKey: 'procurement.request.purchaseMethod', width: 120, sortable: 'purchase_method' },
  { prop: 'budgetAmount', labelKey: 'procurement.request.budgetAmount', width: 120, sortable: 'budget_amount' },
  { prop: 'expectDate', labelKey: 'procurement.request.expectDate', width: 110, sortable: 'expect_date' },
  { prop: 'status', labelKey: 'procurement.request.status', width: 100, sortable: 'status' },
  { prop: 'createTime', labelKey: 'procurement.request.createTime', width: 160, sortable: 'create_time' },
]

function rowActions(row: PurchaseRequest): ActionItem[] {
  const s = String(row.status)
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  if (['draft', 'rejected'].includes(s)) acts.push({ key: 'edit', tip: 'common.action.edit', perm: 'procurement:request:edit' })
  if (['draft', 'rejected'].includes(s)) {
    acts.push({ key: 'submit', tip: 'procurement.request.submit', perm: 'procurement:request:submit' })
  }
  if (s === 'approved') {
    acts.push({ key: 'generate', tip: 'procurement.request.generateContract', icon: 'DocumentAdd', perm: 'procurement:contract:create' })
  }
  if (['draft', 'rejected', 'approved'].includes(s)) {
    acts.push({ key: 'void', tip: 'procurement.request.void', icon: 'FolderDelete', danger: true, perm: 'procurement:request:edit' })
  }
  if (s === 'draft') acts.push({ key: 'delete', tip: 'common.action.delete', perm: 'procurement:request:delete' })
  return acts
}

function onRowAction(key: string, row: PurchaseRequest) {
  if (key === 'detail') openDetail(row.id)
  else if (key === 'edit') openEdit(row)
  else if (key === 'submit') void doSubmit(row)
  else if (key === 'generate') openGenerate(row)
  else if (key === 'void') void doVoid(row)
  else if (key === 'delete') void remove(row)
}

/* ---------- form ---------- */
const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  title: '',
  taskId: null as number | null,
  purchaseMethod: '',
  budgetAmount: null as number | null,
  expectDate: '',
  reason: '',
  remark: '',
  items: [] as PurchaseRequestItem[],
  version: null as number | null,
})

const taskOpts = ref<{ value: number; label: string }[]>([])
const taskLoading = ref(false)

async function searchTasks(q: string) {
  taskLoading.value = true
  try {
    const data = await listTasks({ page: 1, size: 20, q: q || undefined })
    taskOpts.value = (data.items ?? []).map((x: Task) => ({
      value: x.id,
      label: `${x.taskNo} ${x.taskName}`,
    }))
  } catch {
    taskOpts.value = []
  } finally {
    taskLoading.value = false
  }
}

function blankItem(): PurchaseRequestItem {
  return { itemName: '', spec: '', unit: '', quantity: 1, estimatePrice: null, remark: '' }
}

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('procurement.request.create')
  Object.assign(form, {
    title: '',
    taskId: null,
    purchaseMethod: '',
    budgetAmount: null,
    expectDate: '',
    reason: '',
    remark: '',
    items: [blankItem()],
    version: null,
  })
  taskOpts.value = []
  dialogVisible.value = true
}

function openEdit(row: PurchaseRequest) {
  editingId.value = row.id
  dialogTitle.value = t('procurement.request.edit')
  Object.assign(form, {
    title: row.title,
    taskId: row.taskId,
    purchaseMethod: row.purchaseMethod ?? '',
    budgetAmount: row.budgetAmount === null ? null : Number(row.budgetAmount),
    expectDate: row.expectDate ?? '',
    reason: row.reason ?? '',
    remark: row.remark ?? '',
    items: (row.items ?? []).map((i) => ({ ...i })),
    version: row.version ?? null,
  })
  taskOpts.value = row.taskId ? [{ value: row.taskId, label: `${row.taskNo} ${row.taskName}` }] : []
  dialogVisible.value = true
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  const items = form.items.filter((i) => i.itemName.trim())
  saving.value = true
  try {
    const payload = {
      title: form.title,
      taskId: form.taskId,
      purchaseMethod: form.purchaseMethod,
      budgetAmount: form.budgetAmount,
      expectDate: form.expectDate,
      reason: form.reason,
      remark: form.remark,
      items,
      version: form.version,
    }
    if (editingId.value) await updatePurchaseRequest(editingId.value, payload)
    else await createPurchaseRequest(payload)
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function doSubmit(row: PurchaseRequest) {
  try {
    await ElMessageBox.confirm(t('procurement.request.submitConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await submitPurchaseRequest(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doVoid(row: PurchaseRequest) {
  try {
    await ElMessageBox.confirm(t('procurement.request.voidConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await voidPurchaseRequest(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function remove(row: PurchaseRequest) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deletePurchaseRequest(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------- detail drawer ---------- */
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<PurchaseRequestDetail | null>(null)

async function openDetail(id: number) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getPurchaseRequest(id)
  } catch {
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

// 深链互跳：/procurement/requests?detail=<id>
watch(
  () => route.query.detail,
  (v) => {
    const id = Number(v)
    if (!id) return
    void openDetail(id)
    router.replace({ query: { ...route.query, detail: undefined } })
  },
  { immediate: true },
)

function openLinkedContract() {
  if (!detail.value?.contractId) return
  router.push({ path: '/procurement/contracts', query: { detail: detail.value.contractId } })
}

/* ---------- generate contract ---------- */
const genVisible = ref(false)
const genSaving = ref(false)
const genRequestId = ref<number | null>(null)
const genForm = reactive({
  supplierId: null as number | null,
  name: '',
  amount: null as number | null,
})
const supplierOpts = ref<CustomerOption[]>([])
const supplierLoading = ref(false)

async function searchSuppliers(q: string) {
  supplierLoading.value = true
  try {
    supplierOpts.value = await customerOptions(q, 20, 'supplier')
  } catch {
    supplierOpts.value = []
  } finally {
    supplierLoading.value = false
  }
}

function openGenerate(row: PurchaseRequest) {
  genRequestId.value = row.id
  Object.assign(genForm, { supplierId: null, name: `${row.title}`, amount: row.budgetAmount === null ? null : Number(row.budgetAmount) })
  supplierOpts.value = []
  genVisible.value = true
}

async function doGenerate() {
  if (!genRequestId.value || !genForm.supplierId) return
  genSaving.value = true
  try {
    const c = await generateContract(genRequestId.value, {
      supplierId: genForm.supplierId,
      name: genForm.name || undefined,
      amount: genForm.amount,
    })
    ElMessage.success(t('common.message.saveSuccess'))
    genVisible.value = false
    detailVisible.value = false
    list.refresh()
    router.push({ path: '/procurement/contracts', query: { detail: c.id } })
  } catch {
    /* http notifies */
  } finally {
    genSaving.value = false
  }
}

function methodLabel(value: unknown) {
  const v = String(value ?? '')
  return methodOpts.opts.value.find((x) => x.value === v)?.label || v || '-'
}

function fmtAmount(v: unknown) {
  const n = Number(v ?? 0)
  return Number.isFinite(n) && v !== null && v !== '' ? n.toLocaleString() : '-'
}
</script>

<template>
  <ListPage :title="t('procurement.request.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'procurement:request:create'" type="primary" @click="openCreate">
        {{ t('procurement.request.create') }}
      </el-button>
      <ExportButton v-permission="'procurement:request:list:export'" :export-fn="() => list.exportList()" />
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
        @sort-change="list.onSortChange"
      >
        <template #requestNo="{ row }">
          <el-button link type="primary" @click="openDetail(row.id)">{{ row.requestNo || '-' }}</el-button>
        </template>
        <template #purchaseMethod="{ row }">{{ methodLabel(row.purchaseMethod) }}</template>
        <template #budgetAmount="{ row }">{{ fmtAmount(row.budgetAmount) }}</template>
        <template #taskNo="{ row }">{{ row.taskNo || '-' }}</template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="common.status" />
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="130" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar :actions="rowActions(row as unknown as PurchaseRequest)" @select="(k) => onRowAction(k, row as unknown as PurchaseRequest)" />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="860px" append-to-body>
    <el-form ref="formRef" :model="form" label-width="110px">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('procurement.request.requestTitle')" prop="title" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-input v-model="form.title" :maxlength="255" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('procurement.request.task')">
            <el-select
              v-model="form.taskId"
              clearable
              filterable
              remote
              :remote-method="searchTasks"
              :loading="taskLoading"
              :placeholder="t('procurement.request.taskPlaceholder')"
              style="width: 100%"
              @focus="!taskOpts.length && searchTasks('')"
            >
              <el-option v-for="o in taskOpts" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('procurement.request.purchaseMethod')">
            <el-select v-model="form.purchaseMethod" clearable :placeholder="t('common.form.placeholderSelect')" style="width: 100%">
              <el-option v-for="o in methodOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('procurement.request.budgetAmount')">
            <el-input-number v-model="form.budgetAmount" :min="0" :precision="2" :controls="false" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('procurement.request.expectDate')">
            <el-date-picker v-model="form.expectDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <el-form-item :label="t('procurement.request.reason')">
            <el-input v-model="form.reason" type="textarea" :rows="2" :maxlength="2000" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item :label="t('procurement.request.items')">
        <div class="items-editor">
          <el-table :data="form.items" border size="small">
            <el-table-column :label="t('procurement.item.itemName')" min-width="160">
              <template #default="{ row }"><el-input v-model="row.itemName" :maxlength="255" /></template>
            </el-table-column>
            <el-table-column :label="t('procurement.item.spec')" width="140">
              <template #default="{ row }"><el-input v-model="row.spec" :maxlength="255" /></template>
            </el-table-column>
            <el-table-column :label="t('procurement.item.unit')" width="90">
              <template #default="{ row }"><el-input v-model="row.unit" :maxlength="16" /></template>
            </el-table-column>
            <el-table-column :label="t('procurement.item.quantity')" width="110">
              <template #default="{ row }">
                <el-input-number v-model="row.quantity" :min="0.01" :precision="2" :controls="false" style="width: 100%" />
              </template>
            </el-table-column>
            <el-table-column :label="t('procurement.item.estimatePrice')" width="120">
              <template #default="{ row }">
                <el-input-number v-model="row.estimatePrice" :min="0" :precision="2" :controls="false" style="width: 100%" />
              </template>
            </el-table-column>
            <el-table-column :label="t('common.action.operate')" width="70" align="center">
              <template #default="{ $index }">
                <el-button link type="danger" @click="form.items.splice($index, 1)">{{ t('common.action.delete') }}</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-button class="add-item" size="small" @click="form.items.push(blankItem())">
            {{ t('procurement.item.addItem') }}
          </el-button>
        </div>
      </el-form-item>

      <el-form-item :label="t('procurement.request.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" :maxlength="2000" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <el-drawer v-model="detailVisible" size="720px">
    <template #header>
      <div class="drawer-header">
        <span class="drawer-title">{{ detail?.title || t('procurement.request.detail') }}</span>
        <StatusTag v-if="detail" :status="detail.status" i18n-prefix="common.status" />
      </div>
    </template>
    <div v-loading="detailLoading" class="drawer-body">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('procurement.request.requestNo')">{{ detail.requestNo || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.request.purchaseMethod')">{{ methodLabel(detail.purchaseMethod) }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.request.task')">
            {{ detail.taskNo ? `${detail.taskNo} ${detail.taskName}` : '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('procurement.request.expectDate')">{{ detail.expectDate || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.request.budgetAmount')">{{ fmtAmount(detail.budgetAmount) }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.request.createTime')">{{ detail.createTime }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.request.reason')" :span="2">{{ detail.reason || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.request.remark')" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-title">{{ t('procurement.request.items') }}</div>
        <el-table :data="detail.items" border stripe size="small">
          <el-table-column :label="t('procurement.item.itemName')" prop="itemName" min-width="140" />
          <el-table-column :label="t('procurement.item.spec')" prop="spec" width="120" />
          <el-table-column :label="t('procurement.item.unit')" prop="unit" width="70" />
          <el-table-column :label="t('procurement.item.quantity')" prop="quantity" width="90" align="right" />
          <el-table-column :label="t('procurement.item.estimatePrice')" width="110" align="right">
            <template #default="{ row }">{{ fmtAmount(row.estimatePrice) }}</template>
          </el-table-column>
        </el-table>

        <div class="section-title">{{ t('procurement.request.linkedContract') }}</div>
        <div v-if="detail.contractId" class="link-row">
          <el-button link type="primary" @click="openLinkedContract">
            {{ detail.contractNo || `#${detail.contractId}` }}
          </el-button>
          <StatusTag :status="detail.contractStatus || ''" i18n-prefix="common.status" />
        </div>
        <div v-else class="link-row">
          <span class="muted">{{ t('procurement.request.noContract') }}</span>
          <el-button
            v-if="detail.status === 'approved'"
            v-permission="'procurement:contract:create'"
            type="primary"
            size="small"
            @click="openGenerate(detail)"
          >
            {{ t('procurement.request.generateContract') }}
          </el-button>
        </div>

        <div class="section-title">{{ t('procurement.request.timeline') }}</div>
        <ApprovalTimeline :records="detail.timeline ?? []" />
      </template>
    </div>
  </el-drawer>

  <el-dialog v-model="genVisible" :title="t('procurement.request.generateContract')" width="520px" append-to-body>
    <p class="muted gen-tip">{{ t('procurement.request.generateTip') }}</p>
    <el-form :model="genForm" label-width="100px">
      <el-form-item :label="t('procurement.contract.supplier')" required>
        <el-select
          v-model="genForm.supplierId"
          filterable
          remote
          :remote-method="searchSuppliers"
          :loading="supplierLoading"
          :placeholder="t('procurement.contract.supplierPlaceholder')"
          style="width: 100%"
          @focus="!supplierOpts.length && searchSuppliers('')"
        >
          <el-option v-for="o in supplierOpts" :key="o.id" :label="o.label" :value="Number(o.id)" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('procurement.contract.name')">
        <el-input v-model="genForm.name" :maxlength="255" />
      </el-form-item>
      <el-form-item :label="t('procurement.contract.amount')">
        <el-input-number v-model="genForm.amount" :min="0" :precision="2" :controls="false" style="width: 100%" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="genVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="genSaving" :disabled="!genForm.supplierId" @click="doGenerate">
        {{ t('common.action.save') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.drawer-header {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.drawer-title {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
}

.drawer-body {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.section-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.link-row {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.muted {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.gen-tip {
  margin: 0 0 var(--bs-space-3);
}

.items-editor {
  width: 100%;
}

.add-item {
  margin-top: var(--bs-space-2);
}
</style>
