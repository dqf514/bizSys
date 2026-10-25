<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import RemoteSelect, { type RemoteOption } from '@/components/form/RemoteSelect.vue'
import { useListPage } from '@/composables/useListPage'
import {
  listInvoices,
  invoiceCounts,
  updateInvoice,
  exportInvoices,
  applyInvoice,
  listSettlements,
} from '@/api/finance'
import type { InvoiceListItem } from '@/api/types'

defineOptions({ name: 'InvoiceList' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'finance.invoice.searchQ', placeholderKey: 'finance.invoice.placeholderQ', width: 260 },
]

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'approving', labelKey: 'finance.invoice.status.approving', count: 0 },
  { value: 'issued', labelKey: 'finance.invoice.status.issued', count: 0 },
])

const counts = ref<Record<string, number>>({})

async function loadCounts() {
  try {
    counts.value = (await invoiceCounts()) ?? {}
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

const list = useListPage<InvoiceListItem>({
  fetch: async (params) => {
    const data = await listInvoices({
      ...params,
      q: searchModel.value.q || undefined,
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportInvoices({
      ...params,
      q: searchModel.value.q || undefined,
    }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

function fmtAmount(row: Record<string, unknown>, prop: string) {
  const n = Number(row[prop] ?? 0)
  return Number.isFinite(n) ? n.toLocaleString() : String(row[prop] ?? '-')
}

const columns: ListColumn[] = [
  { prop: 'invoiceNo', labelKey: 'finance.invoice.invoiceNo', width: 160, fixed: 'left', sortable: 'invoice_no' },
  { prop: 'settlementNo', labelKey: 'finance.invoice.settlementNo', width: 150 },
  { prop: 'taskNo', labelKey: 'finance.invoice.taskNo', width: 140 },
  { prop: 'customerName', labelKey: 'finance.invoice.customerName', minWidth: 140 },
  { prop: 'amount', labelKey: 'finance.invoice.amount', width: 120, align: 'right', sortable: 'amount' },
  { prop: 'invoiceDate', labelKey: 'finance.invoice.invoiceDate', width: 120, sortable: 'invoice_date' },
  { prop: 'status', labelKey: 'common.form.status', width: 100, sortable: 'status' },
  { prop: 'createBy', labelKey: 'finance.invoice.createBy', width: 100 },
  { prop: 'createTime', labelKey: 'finance.invoice.createTime', width: 160, sortable: 'create_time' },
]

/** 仅「已开出未登记票号」可登记 */
function rowActions(row: InvoiceListItem): ActionItem[] {
  if (row.status === 'issued' && !row.invoiceNo) {
    return [{ key: 'registerInvoice', tip: 'finance.invoice.register', icon: 'Postcard', perm: 'finance:invoice:edit' }]
  }
  return []
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

function openInvoiceRegister(row: InvoiceListItem) {
  Object.assign(invoiceForm, {
    invoiceId: row.id,
    invoiceNo: row.invoiceNo ?? '',
    amount: row.amount === undefined || row.amount === null ? undefined : Number(row.amount),
    invoiceDate: row.invoiceDate ?? '',
  })
  invoiceVisible.value = true
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
  } catch {
    /* http notifies */
  } finally {
    invoiceSaving.value = false
  }
}

/* ---------- apply invoice (entry from invoice page) ---------- */
const applyVisible = ref(false)
const applySaving = ref(false)
const applySettlementId = ref<number | null>(null)

function openApply() {
  applySettlementId.value = null
  applyVisible.value = true
}

/** 只允许「待开票」且客户已确认的结算单：与结算列表的行内入口同一规则 */
async function fetchPendingSettlements(q: string): Promise<RemoteOption[]> {
  try {
    const data = await listSettlements({
      q: q || undefined,
      filters: { status: 'pending', confirm_status: 'confirmed' },
      size: 50,
    })
    return (data.items ?? []).map((s) => ({
      id: s.id,
      label: `${s.settlementNo} · ${s.customerName ?? ''}`,
      sub: `¥${Number(s.invoiceableAmount ?? s.amount ?? 0).toLocaleString()}`,
    }))
  } catch {
    return []
  }
}

async function doApply() {
  if (!applySettlementId.value) return
  applySaving.value = true
  try {
    await applyInvoice(applySettlementId.value)
    ElMessage.success(t('common.message.submitSuccess'))
    applyVisible.value = false
    applySettlementId.value = null
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    applySaving.value = false
  }
}
</script>

<template>
  <ListPage :title="t('finance.invoice.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'finance:invoice:apply'" type="primary" @click="openApply">
        {{ t('finance.invoice.apply') }}
      </el-button>
      <ExportButton v-permission="'finance:invoice:export'" :export-fn="() => list.exportList()" />
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
        <template #invoiceNo="{ row }">{{ row.invoiceNo || '-' }}</template>
        <template #amount="{ row }">{{ fmtAmount(row, 'amount') }}</template>
        <template #invoiceDate="{ row }">{{ row.invoiceDate || '-' }}</template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="finance.invoice.status" />
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="90" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar
                :actions="rowActions(row as unknown as InvoiceListItem)"
                @select="openInvoiceRegister(row as unknown as InvoiceListItem)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="invoiceVisible" :title="t('finance.invoice.register')" width="520px" append-to-body>
    <el-form ref="invoiceFormRef" :model="invoiceForm" label-width="110px">
      <el-form-item
        :label="t('finance.invoice.invoiceNo')"
        prop="invoiceNo"
        :rules="[{ required: true, message: t('common.form.required') }]"
      >
        <el-input v-model="invoiceForm.invoiceNo" />
      </el-form-item>
      <el-form-item
        :label="t('finance.invoice.amount')"
        prop="amount"
        :rules="[{ required: true, type: 'number', message: t('common.form.required') }]"
      >
        <el-input-number v-model="invoiceForm.amount" :min="0" :precision="2" style="width: 100%" />
      </el-form-item>
      <el-form-item :label="t('finance.invoice.invoiceDate')">
        <el-date-picker v-model="invoiceForm.invoiceDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="invoiceVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="invoiceSaving" @click="saveInvoice">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="applyVisible" :title="t('finance.invoice.apply')" width="520px" append-to-body>
    <el-form label-width="110px">
      <el-form-item :label="t('finance.invoice.selectSettlement')" required>
        <RemoteSelect v-model="applySettlementId" :fetch="fetchPendingSettlements" />
      </el-form-item>
      <p style="margin: 0; font-size: 12px; color: var(--bs-color-fg-muted)">{{ t('finance.invoice.applyHint') }}</p>
    </el-form>
    <template #footer>
      <el-button @click="applyVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :disabled="!applySettlementId" :loading="applySaving" @click="doApply">
        {{ t('common.action.submit') }}
      </el-button>
    </template>
  </el-dialog>
</template>
