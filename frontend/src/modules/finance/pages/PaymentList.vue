<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import PaymentCreateDialog from '../components/PaymentCreateDialog.vue'
import { useListPage } from '@/composables/useListPage'
import { useDictOptions } from '@/composables/useDict'
import { listPayments, exportPayments, paymentCounts, submitPayment } from '@/api/finance'
import type { Payment } from '@/api/types'

defineOptions({ name: 'PaymentList' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'finance.payment.searchQ', placeholderKey: 'finance.payment.placeholderQ', width: 260 },
]

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'draft', labelKey: 'finance.payment.status.draft', count: 0 },
  { value: 'approving', labelKey: 'finance.payment.status.approving', count: 0 },
  { value: 'confirmed', labelKey: 'finance.payment.status.confirmed', count: 0 },
  { value: 'rejected', labelKey: 'finance.payment.status.rejected', count: 0 },
])

const counts = ref<Record<string, number>>({})

async function loadCounts() {
  try {
    counts.value = (await paymentCounts()) ?? {}
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

const list = useListPage<Payment>({
  fetch: async (params) => {
    const data = await listPayments({
      ...params,
      q: searchModel.value.q || undefined,
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportPayments({
      ...params,
      q: searchModel.value.q || undefined,
    }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

function fmtAmount(row: Record<string, unknown>) {
  const n = Number(row.amount ?? 0)
  return Number.isFinite(n) ? n.toLocaleString() : String(row.amount ?? '-')
}

const columns: ListColumn[] = [
  { prop: 'paymentNo', labelKey: 'finance.payment.paymentNo', width: 160, fixed: 'left', sortable: 'payment_no' },
  { prop: 'settlementNo', labelKey: 'finance.payment.settlementNo', width: 150 },
  { prop: 'payType', labelKey: 'finance.payment.payType', width: 110, sortable: 'pay_type' },
  { prop: 'payerName', labelKey: 'finance.payment.payerName', minWidth: 150, sortable: 'payer_name' },
  { prop: 'amount', labelKey: 'finance.payment.amount', width: 120, align: 'right', sortable: 'amount' },
  { prop: 'bank', labelKey: 'finance.payment.bank', minWidth: 150 },
  { prop: 'paidAt', labelKey: 'finance.payment.paidAt', width: 120, sortable: 'paid_at' },
  { prop: 'status', labelKey: 'common.form.status', width: 110, sortable: 'status' },
  { prop: 'createBy', labelKey: 'finance.payment.createBy', width: 100 },
]

/** F5：到账登记只是登记，必须提交复核；复核通过才计入结算单已到账金额 */
function rowActions(row: Payment): ActionItem[] {
  const acts: ActionItem[] = []
  if (row.status === 'draft' || row.status === 'rejected') {
    acts.push({ key: 'submit', tip: 'finance.payment.submit', perm: 'finance:payment:submit' })
  }
  return acts
}

function onRowAction(key: string, row: Payment) {
  if (key === 'submit') void doSubmit(row)
}

async function doSubmit(row: Payment) {
  try {
    await ElMessageBox.confirm(t('finance.payment.submitConfirm'), t('common.action.confirm'), {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await submitPayment(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

const payTypeOpts = useDictOptions('pay_type')

const createVisible = ref(false)
</script>

<template>
  <ListPage :title="t('finance.payment.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'finance:payment:create'" type="primary" @click="createVisible = true">
        {{ t('finance.payment.create') }}
      </el-button>
      <ExportButton v-permission="'finance:payment:export'" :export-fn="() => list.exportList()" />
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
        <template #payType="{ row }">
          {{ payTypeOpts.opts.value.find((x) => x.value === row.payType)?.label || row.payType || '-' }}
        </template>
        <template #amount="{ row }">{{ fmtAmount(row) }}</template>
        <template #bank="{ row }">{{ row.bank || '-' }}</template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="finance.payment.status" />
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="120" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar :actions="rowActions(row as unknown as Payment)" @select="(k) => onRowAction(k, row as unknown as Payment)" />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <PaymentCreateDialog v-model="createVisible" @saved="list.refresh()" />
</template>
