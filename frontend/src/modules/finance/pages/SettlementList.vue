<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import RemoteSelect, { type RemoteOption } from '@/components/form/RemoteSelect.vue'
import PaymentCreateDialog from '../components/PaymentCreateDialog.vue'
import SettlementDetailDrawer from '../components/SettlementDetailDrawer.vue'
import { useListPage } from '@/composables/useListPage'
import {
  listSettlements,
  settlementTaskOptions,
  createSettlement,
  getSettlement,
  applyInvoice,
  submitSettlement,
  updateInvoice,
  exportSettlements,
} from '@/api/finance'
import type { Settlement } from '@/api/types'

defineOptions({ name: 'SettlementList' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'finance.settlement.searchQ', placeholderKey: 'finance.settlement.placeholderQ', width: 260 },
]

const statusTabs: StatusTabItem[] = [
  { value: 'approving', labelKey: 'finance.settlement.status.approving' },
  { value: 'pending', labelKey: 'finance.settlement.status.pending' },
  { value: 'invoicing', labelKey: 'finance.settlement.status.invoicing' },
  { value: 'invoiced', labelKey: 'finance.settlement.status.invoiced' },
  { value: 'paid', labelKey: 'finance.settlement.status.paid' },
  { value: 'rejected', labelKey: 'finance.settlement.status.rejected' },
  { value: 'all', labelKey: 'common.action.all' },
]

const list = useListPage<Settlement>({
  fetch: async (params) => {
    const data = await listSettlements({
      ...params,
      q: searchModel.value.q || undefined,
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportSettlements({
      ...params,
      q: searchModel.value.q || undefined,
    }),
  defaultStatus: 'all',
})

function fmtAmount(row: Record<string, unknown>, prop: string) {
  const n = Number(row[prop] ?? 0)
  return Number.isFinite(n) ? n.toLocaleString() : String(row[prop] ?? '-')
}

const columns: ListColumn[] = [
  { prop: 'settlementNo', labelKey: 'finance.settlement.settlementNo', width: 150, fixed: 'left' },
  { prop: 'taskNo', labelKey: 'finance.settlement.taskNo', width: 140 },
  { prop: 'customerName', labelKey: 'finance.settlement.customerName', minWidth: 140 },
  { prop: 'contractNo', labelKey: 'finance.settlement.contractNo', width: 140 },
  { prop: 'amount', labelKey: 'finance.settlement.amount', width: 120 },
  { prop: 'invoiceableAmount', labelKey: 'finance.settlement.invoiceableAmount', width: 120 },
  { prop: 'status', labelKey: 'common.form.status', width: 110 },
  { prop: 'createBy', labelKey: 'finance.settlement.createBy', width: 100 },
  { prop: 'createTime', labelKey: 'finance.settlement.createTime', width: 160 },
]

/* ---------- create settlement dialog ---------- */const createVisible = ref(false)
const createFormRef = ref<FormInstance>()
const createSaving = ref(false)
const createForm = reactive({
  taskId: null as number | null,
  amount: undefined as number | undefined,
  invoiceableAmount: undefined as number | undefined,
  remark: '',
})
let invoiceableDirty = false

watch(
  () => createForm.amount,
  (v) => {
    if (!invoiceableDirty) createForm.invoiceableAmount = v
  },
)

async function fetchTaskOptions(q: string): Promise<RemoteOption[]> {
  try {
    const options = await settlementTaskOptions(q)
    return (options ?? []).map((x) => ({ id: x.value, label: x.label, sub: x.sub }))
  } catch {
    return []
  }
}

function openCreate() {
  invoiceableDirty = false
  Object.assign(createForm, { taskId: null, amount: undefined, invoiceableAmount: undefined, remark: '' })
  createVisible.value = true
}

async function saveCreate() {
  if (!createFormRef.value) return
  const ok = await createFormRef.value.validate().catch(() => false)
  if (!ok) return
  if (!createForm.taskId) return
  createSaving.value = true
  try {
    await createSettlement({
      taskId: createForm.taskId,
      amount: Number(createForm.amount),
      invoiceableAmount:
        createForm.invoiceableAmount === undefined ? undefined : Number(createForm.invoiceableAmount),
      remark: createForm.remark || undefined,
    })
    ElMessage.success(t('common.message.createSuccess'))
    createVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    createSaving.value = false
  }
}

/* ---------- detail drawer (shared component) ---------- */
const detailVisible = ref(false)
const detailId = ref<number | null>(null)
const drawerRef = ref<InstanceType<typeof SettlementDetailDrawer>>()

function openDetail(row: Settlement) {
  detailId.value = row.id
  detailVisible.value = true
}

/* ---------- apply invoice ---------- */
async function doApplyInvoice(row: Settlement) {
  try {
    await ElMessageBox.confirm(t('finance.settlement.applyInvoiceConfirm'), t('common.action.confirm'), {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await applyInvoice(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------- resubmit rejected settlement ---------- */
async function doResubmit(row: Settlement) {
  try {
    await ElMessageBox.confirm(t('finance.settlement.resubmitConfirm'), t('common.action.confirm'), {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await submitSettlement(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

/* ---------- register invoice dialog ---------- */
const invoiceVisible = ref(false)
const invoiceFormRef = ref<FormInstance>()
const invoiceSaving = ref(false)
const invoiceForm = reactive({
  invoiceId: null as number | null,
  invoiceNo: '',
  amount: undefined as number | undefined,
  invoiceDate: '',
})

async function openInvoiceRegister(row: Settlement) {
  try {
    const d = await getSettlement(row.id)
    const invoices = d.invoices ?? []
    const inv = invoices.find((i) => !i.invoiceNo) ?? invoices[invoices.length - 1]
    if (!inv) {
      ElMessage.warning(t('finance.settlement.noInvoice'))
      return
    }
    Object.assign(invoiceForm, {
      invoiceId: inv.id,
      invoiceNo: inv.invoiceNo ?? '',
      amount: inv.amount === undefined || inv.amount === null ? undefined : Number(inv.amount),
      invoiceDate: inv.invoiceDate ?? '',
    })
    invoiceVisible.value = true
  } catch {
    /* http notifies */
  }
}

async function saveInvoice() {
  if (!invoiceFormRef.value || !invoiceForm.invoiceId) return
  const ok = await invoiceFormRef.value.validate().catch(() => false)
  if (!ok) return
  invoiceSaving.value = true
  try {
    await updateInvoice(invoiceForm.invoiceId, {
      invoiceNo: invoiceForm.invoiceNo,
      amount: Number(invoiceForm.amount),
      invoiceDate: invoiceForm.invoiceDate || undefined,
    })
    ElMessage.success(t('common.message.updateSuccess'))
    invoiceVisible.value = false
    list.refresh()
    if (detailVisible.value) drawerRef.value?.reload()
  } catch {
    /* http notifies */
  } finally {
    invoiceSaving.value = false
  }
}

/* ---------- payment registration (shared dialog) ---------- */
const paymentVisible = ref(false)
const paymentPreset = ref<Settlement | null>(null)

function openPaymentRegister(row: Settlement) {
  paymentPreset.value = row
  paymentVisible.value = true
}
</script>

<template>
  <ListPage :title="t('finance.settlement.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'finance:settlement:create'" type="primary" @click="openCreate">
        {{ t('finance.settlement.create') }}
      </el-button>
      <ExportButton v-permission="'finance:settlement:export'" :export-fn="() => list.exportList()" />
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
        <template #settlementNo="{ row }">
          <el-button link type="primary" @click="openDetail(row as unknown as Settlement)">
            {{ row.settlementNo }}
          </el-button>
        </template>
        <template #amount="{ row }">{{ fmtAmount(row, 'amount') }}</template>
        <template #invoiceableAmount="{ row }">{{ fmtAmount(row, 'invoiceableAmount') }}</template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="finance.settlement.status" />
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="300" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openDetail(row as unknown as Settlement)">
                {{ t('common.action.detail') }}
              </el-button>
              <el-button
                v-if="row.status === 'rejected'"
                v-permission="'finance:settlement:create'"
                link
                type="warning"
                @click="doResubmit(row as unknown as Settlement)"
              >
                {{ t('finance.settlement.resubmit') }}
              </el-button>
              <el-button
                v-if="row.status === 'pending'"
                v-permission="'finance:invoice:apply'"
                link
                type="warning"
                @click="doApplyInvoice(row as unknown as Settlement)"
              >
                {{ t('finance.settlement.applyInvoice') }}
              </el-button>
              <el-button
                v-if="row.status === 'invoiced'"
                v-permission="'finance:invoice:edit'"
                link
                type="primary"
                @click="openInvoiceRegister(row as unknown as Settlement)"
              >
                {{ t('finance.settlement.registerInvoice') }}
              </el-button>
              <el-button
                v-if="row.status === 'invoiced'"
                v-permission="'finance:payment:create'"
                link
                type="success"
                @click="openPaymentRegister(row as unknown as Settlement)"
              >
                {{ t('finance.settlement.registerPayment') }}
              </el-button>
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="createVisible" :title="t('finance.settlement.create')" width="560px" append-to-body>
    <el-form ref="createFormRef" :model="createForm" label-width="110px">
      <el-form-item
        :label="t('finance.settlement.selectTask')"
        prop="taskId"
        :rules="[{ required: true, message: t('common.form.required') }]"
      >
        <RemoteSelect v-model="createForm.taskId" :fetch="fetchTaskOptions" />
      </el-form-item>
      <el-form-item
        :label="t('finance.settlement.amount')"
        prop="amount"
        :rules="[{ required: true, type: 'number', message: t('common.form.required') }]"
      >
        <el-input-number v-model="createForm.amount" :min="0" :precision="2" style="width: 100%" />
      </el-form-item>
      <el-form-item :label="t('finance.settlement.invoiceableAmount')">
        <el-input-number
          v-model="createForm.invoiceableAmount"
          :min="0"
          :precision="2"
          style="width: 100%"
          @change="invoiceableDirty = true"
        />
      </el-form-item>
      <el-form-item :label="t('finance.settlement.remark')">
        <el-input v-model="createForm.remark" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="createVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="createSaving" @click="saveCreate">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="invoiceVisible" :title="t('finance.settlement.registerInvoice')" width="520px" append-to-body>
    <el-form ref="invoiceFormRef" :model="invoiceForm" label-width="110px">
      <el-form-item
        :label="t('finance.settlement.invoiceNo')"
        prop="invoiceNo"
        :rules="[{ required: true, message: t('common.form.required') }]"
      >
        <el-input v-model="invoiceForm.invoiceNo" />
      </el-form-item>
      <el-form-item
        :label="t('finance.settlement.amount')"
        prop="amount"
        :rules="[{ required: true, type: 'number', message: t('common.form.required') }]"
      >
        <el-input-number v-model="invoiceForm.amount" :min="0" :precision="2" style="width: 100%" />
      </el-form-item>
      <el-form-item :label="t('finance.settlement.invoiceDate')">
        <el-date-picker v-model="invoiceForm.invoiceDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="invoiceVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="invoiceSaving" @click="saveInvoice">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <PaymentCreateDialog v-model="paymentVisible" :preset="paymentPreset" @saved="list.refresh()" />

  <SettlementDetailDrawer ref="drawerRef" v-model="detailVisible" :settlement-id="detailId" />
</template>
