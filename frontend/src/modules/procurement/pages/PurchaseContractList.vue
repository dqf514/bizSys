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
  listPurchaseContracts,
  purchaseContractCounts,
  getPurchaseContract,
  createPurchaseContract,
  updatePurchaseContract,
  deletePurchaseContract,
  submitPurchaseContract,
  voidPurchaseContract,
  exportPurchaseContracts,
} from '@/api/procurement'
import { customerOptions } from '@/api/crm'
import type { CustomerOption, PurchaseContract, PurchaseContractDetail } from '@/api/types'

defineOptions({ name: 'PurchaseContractList' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const payCycleOpts = useDictOptions('pay_cycle')
const deliveryOpts = useDictOptions('delivery_way')

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'procurement.contract.searchName', placeholderKey: 'procurement.contract.placeholderName', width: 240 },
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
    counts.value = (await purchaseContractCounts()) ?? {}
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

const list = useListPage<PurchaseContract>({
  fetch: async (params) => {
    const data = await listPurchaseContracts({ ...params, q: searchModel.value.q || undefined })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) => exportPurchaseContracts({ ...params, q: searchModel.value.q || undefined }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'contractNo', labelKey: 'procurement.contract.contractNo', width: 150, fixed: 'left', sortable: 'contract_no' },
  { prop: 'name', labelKey: 'procurement.contract.name', minWidth: 200, fixed: 'left', sortable: 'name' },
  { prop: 'supplierName', labelKey: 'procurement.contract.supplier', minWidth: 160, sortable: 'supplier_name' },
  { prop: 'requestNo', labelKey: 'procurement.contract.requestNo', width: 140 },
  { prop: 'amount', labelKey: 'procurement.contract.amount', width: 120, sortable: 'amount' },
  { prop: 'signDate', labelKey: 'procurement.contract.signDate', width: 110, sortable: 'sign_date' },
  { prop: 'handlerName', labelKey: 'procurement.contract.handlerName', width: 100 },
  { prop: 'status', labelKey: 'procurement.contract.status', width: 100, sortable: 'status' },
  { prop: 'createTime', labelKey: 'procurement.contract.createTime', width: 160, sortable: 'create_time' },
]

function rowActions(row: PurchaseContract): ActionItem[] {
  const s = String(row.status)
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  if (['draft', 'rejected'].includes(s)) acts.push({ key: 'edit', tip: 'common.action.edit', perm: 'procurement:contract:edit' })
  if (['draft', 'rejected'].includes(s)) {
    acts.push({ key: 'submit', tip: 'procurement.contract.submit', perm: 'procurement:contract:submit' })
  }
  if (['draft', 'rejected', 'approved'].includes(s)) {
    acts.push({ key: 'void', tip: 'procurement.contract.void', icon: 'FolderDelete', danger: true, perm: 'procurement:contract:edit' })
  }
  if (s === 'draft') acts.push({ key: 'delete', tip: 'common.action.delete', perm: 'procurement:contract:delete' })
  return acts
}

function onRowAction(key: string, row: PurchaseContract) {
  if (key === 'detail') openDetail(row.id)
  else if (key === 'edit') openEdit(row)
  else if (key === 'submit') void doSubmit(row)
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
  name: '',
  supplierId: null as number | null,
  requestId: null as number | null,
  amount: null as number | null,
  signDate: '',
  startDate: '',
  endDate: '',
  payCycle: '',
  delivery: '',
  remark: '',
  version: null as number | null,
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

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('procurement.contract.create')
  Object.assign(form, {
    name: '',
    supplierId: null,
    requestId: null,
    amount: null,
    signDate: '',
    startDate: '',
    endDate: '',
    payCycle: '',
    delivery: '',
    remark: '',
    version: null,
  })
  supplierOpts.value = []
  dialogVisible.value = true
}

function openEdit(row: PurchaseContract) {
  editingId.value = row.id
  dialogTitle.value = t('procurement.contract.edit')
  Object.assign(form, {
    name: row.name,
    supplierId: row.supplierId,
    requestId: row.requestId,
    amount: row.amount === null ? null : Number(row.amount),
    signDate: row.signDate ?? '',
    startDate: row.startDate ?? '',
    endDate: row.endDate ?? '',
    payCycle: row.payCycle ?? '',
    delivery: row.delivery ?? '',
    remark: row.remark ?? '',
    version: row.version ?? null,
  })
  supplierOpts.value = [{ id: row.supplierId, label: row.supplierName }]
  dialogVisible.value = true
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    const payload = {
      name: form.name,
      supplierId: form.supplierId as number,
      requestId: form.requestId,
      amount: form.amount,
      signDate: form.signDate,
      startDate: form.startDate,
      endDate: form.endDate,
      payCycle: form.payCycle,
      delivery: form.delivery,
      remark: form.remark,
      version: form.version,
    }
    if (editingId.value) await updatePurchaseContract(editingId.value, payload)
    else await createPurchaseContract(payload)
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function doSubmit(row: PurchaseContract) {
  try {
    await ElMessageBox.confirm(t('procurement.contract.submitConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await submitPurchaseContract(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function doVoid(row: PurchaseContract) {
  try {
    await ElMessageBox.confirm(t('procurement.contract.voidConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await voidPurchaseContract(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function remove(row: PurchaseContract) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deletePurchaseContract(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------- detail drawer ---------- */
const detailVisible = ref(false)
const detailLoading = ref(false)
const detail = ref<PurchaseContractDetail | null>(null)

async function openDetail(id: number) {
  detailVisible.value = true
  detailLoading.value = true
  try {
    detail.value = await getPurchaseContract(id)
  } catch {
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

// 深链互跳：/procurement/contracts?detail=<id>
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

function openLinkedRequest() {
  if (!detail.value?.requestId) return
  router.push({ path: '/procurement/requests', query: { detail: detail.value.requestId } })
}

function openStockOrder(orderId: number) {
  router.push({ path: '/procurement/stock', query: { detail: orderId } })
}

function payCycleLabel(value: unknown) {
  const v = String(value ?? '')
  return payCycleOpts.opts.value.find((x) => x.value === v)?.label || v || '-'
}

function deliveryLabel(value: unknown) {
  const v = String(value ?? '')
  return deliveryOpts.opts.value.find((x) => x.value === v)?.label || v || '-'
}

function fmtAmount(v: unknown) {
  const n = Number(v ?? 0)
  return Number.isFinite(n) && v !== null && v !== '' ? n.toLocaleString() : '-'
}
</script>

<template>
  <ListPage :title="t('procurement.contract.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'procurement:contract:create'" type="primary" @click="openCreate">
        {{ t('procurement.contract.create') }}
      </el-button>
      <ExportButton v-permission="'procurement:contract:list:export'" :export-fn="() => list.exportList()" />
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
        <template #contractNo="{ row }">
          <el-button link type="primary" @click="openDetail(row.id)">{{ row.contractNo || '-' }}</el-button>
        </template>
        <template #amount="{ row }">{{ fmtAmount(row.amount) }}</template>
        <template #requestNo="{ row }">{{ row.requestNo || '-' }}</template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="common.status" />
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="130" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar :actions="rowActions(row as unknown as PurchaseContract)" @select="(k) => onRowAction(k, row as unknown as PurchaseContract)" />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="720px" append-to-body>
    <p class="muted tip">{{ t('procurement.contract.countersignTip') }}</p>
    <el-form ref="formRef" :model="form" label-width="110px">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item :label="t('procurement.contract.name')" prop="name" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-input v-model="form.name" :maxlength="255" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('procurement.contract.supplier')" prop="supplierId" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-select
              v-model="form.supplierId"
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
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('procurement.contract.amount')">
            <el-input-number v-model="form.amount" :min="0" :precision="2" :controls="false" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('procurement.contract.signDate')">
            <el-date-picker v-model="form.signDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('procurement.contract.startDate')">
            <el-date-picker v-model="form.startDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('procurement.contract.endDate')">
            <el-date-picker v-model="form.endDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('procurement.contract.payCycle')">
            <el-select v-model="form.payCycle" clearable :placeholder="t('common.form.placeholderSelect')" style="width: 100%">
              <el-option v-for="o in payCycleOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('procurement.contract.delivery')">
            <el-select v-model="form.delivery" clearable :placeholder="t('common.form.placeholderSelect')" style="width: 100%">
              <el-option v-for="o in deliveryOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <el-form-item :label="t('procurement.contract.remark')">
            <el-input v-model="form.remark" type="textarea" :rows="2" :maxlength="2000" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <el-drawer v-model="detailVisible" size="720px">
    <template #header>
      <div class="drawer-header">
        <span class="drawer-title">{{ detail?.name || t('procurement.contract.detail') }}</span>
        <StatusTag v-if="detail" :status="detail.status" i18n-prefix="common.status" />
      </div>
    </template>
    <div v-loading="detailLoading" class="drawer-body">
      <template v-if="detail">
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('procurement.contract.contractNo')">{{ detail.contractNo || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.contract.supplier')">{{ detail.supplierName }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.contract.amount')">{{ fmtAmount(detail.amount) }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.contract.signDate')">{{ detail.signDate || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.contract.startDate')">{{ detail.startDate || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.contract.endDate')">{{ detail.endDate || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.contract.payCycle')">{{ payCycleLabel(detail.payCycle) }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.contract.delivery')">{{ deliveryLabel(detail.delivery) }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.contract.handlerName')">{{ detail.handlerName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.contract.createTime')">{{ detail.createTime }}</el-descriptions-item>
          <el-descriptions-item :label="t('procurement.contract.remark')" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-title">{{ t('procurement.contract.linkedRequest') }}</div>
        <div class="link-row">
          <el-button v-if="detail.requestId" link type="primary" @click="openLinkedRequest">
            {{ detail.requestNo || `#${detail.requestId}` }}
          </el-button>
          <span v-else class="muted">-</span>
        </div>

        <div class="section-title">{{ t('procurement.contract.stockOrders') }}</div>
        <el-table v-if="detail.stockOrders?.length" :data="detail.stockOrders" border stripe size="small">
          <el-table-column :label="t('procurement.stock.orderNo')" prop="orderNo" width="170">
            <template #default="{ row }">
              <el-button link type="primary" @click="openStockOrder(row.id)">{{ row.orderNo }}</el-button>
            </template>
          </el-table-column>
          <el-table-column :label="t('procurement.stock.orderType')" width="90">
            <template #default="{ row }">
              {{ row.orderType === 'in' ? t('procurement.stock.typeIn') : t('procurement.stock.typeOut') }}
            </template>
          </el-table-column>
          <el-table-column :label="t('procurement.stock.status')" width="110">
            <template #default="{ row }">
              <StatusTag :status="String(row.status)" i18n-prefix="common.status" />
            </template>
          </el-table-column>
        </el-table>
        <span v-else class="muted">-</span>

        <div class="section-title">{{ t('procurement.contract.timeline') }}</div>
        <ApprovalTimeline :records="detail.timeline ?? []" />
      </template>
    </div>
  </el-drawer>
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

.tip {
  margin: 0 0 var(--bs-space-3);
}
</style>
