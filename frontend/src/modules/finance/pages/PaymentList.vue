<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import PaymentCreateDialog from '../components/PaymentCreateDialog.vue'
import { useListPage } from '@/composables/useListPage'
import { useDictOptions } from '@/composables/useDict'
import { listPayments, exportPayments } from '@/api/finance'
import type { Payment } from '@/api/types'

defineOptions({ name: 'PaymentList' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'finance.payment.searchQ', placeholderKey: 'finance.payment.placeholderQ', width: 260 },
]

const list = useListPage<Payment>({
  fetch: async (params) => {
    const data = await listPayments({
      ...params,
      status: undefined,
      q: searchModel.value.q || undefined,
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportPayments({
      ...params,
      status: undefined,
      q: searchModel.value.q || undefined,
    }),
  defaultStatus: '',
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
  { prop: 'createBy', labelKey: 'finance.payment.createBy', width: 100 },
]

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
      </ListTable>
    </template>
  </ListPage>

  <PaymentCreateDialog v-model="createVisible" @saved="list.refresh()" />
</template>
