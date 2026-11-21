<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useListPage } from '@/composables/useListPage'
import {
  listQuotations,
  quotationCounts,
  deleteQuotation,
  submitQuotation,
  sendQuotation,
  feedbackQuotation,
  quotationToContract,
  exportQuotations,
} from '@/api/sales'
import type { Quotation } from '@/api/types'
import QuotationDetailDrawer from '../components/QuotationDetailDrawer.vue'

defineOptions({ name: 'QuotationList' })

const { t } = useI18n()
const router = useRouter()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'sales.quotation.searchName', placeholderKey: 'sales.quotation.placeholderName', width: 240 },
]

const STATUS_VALUES = ['all', 'draft', 'approving', 'approved', 'rejected', 'sent', 'accepted', 'declined', 'voided']
const statusTabs = ref<StatusTabItem[]>(STATUS_VALUES.map((v) => ({
  value: v,
  labelKey: v === 'all' ? 'common.action.all' : `sales.quotation.status${v.charAt(0).toUpperCase()}${v.slice(1)}`,
  count: 0,
})))

async function loadCounts() {
  try {
    const counts = (await quotationCounts()) ?? {}
    for (const tab of statusTabs.value) tab.count = counts[tab.value] ?? 0
  } catch {
    /* counts optional */
  }
}

onMounted(() => void loadCounts())

const list = useListPage<Quotation>({
  fetch: async (params) => {
    const data = await listQuotations({ ...params, q: searchModel.value.q || undefined })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) => exportQuotations({ ...params, q: searchModel.value.q || undefined }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'quoteNo', labelKey: 'sales.quotation.quoteNo', width: 160, fixed: 'left', sortable: 'quote_no' },
  { prop: 'title', labelKey: 'sales.quotation.quoteTitle', minWidth: 200, sortable: 'title' },
  { prop: 'customerName', labelKey: 'sales.quotation.customerName', minWidth: 150, sortable: 'customer_name' },
  { prop: 'contactName', labelKey: 'sales.quotation.contactName', width: 100 },
  { prop: 'totalAmount', labelKey: 'sales.quotation.totalAmount', width: 120, sortable: 'total_amount' },
  { prop: 'validUntil', labelKey: 'sales.quotation.validUntil', width: 110, sortable: 'valid_until' },
  { prop: 'status', labelKey: 'sales.quotation.status', width: 110, sortable: 'status' },
  { prop: 'sentChannel', labelKey: 'sales.quotation.sentChannel', width: 90 },
  { prop: 'createTime', labelKey: 'contract.contract.createTime', width: 160, sortable: 'create_time' },
]

function rowActions(row: Quotation): ActionItem[] {
  const s = String(row.status)
  const acts: ActionItem[] = [{ key: 'detail', tip: 'common.action.detail' }]
  if (['draft', 'rejected'].includes(s)) {
    acts.push({ key: 'edit', tip: 'common.action.edit', perm: 'sales:quote:edit' })
    acts.push({ key: 'submit', tip: 'sales.quotation.submit', perm: 'sales:quote:submit' })
  }
  if (['approved', 'sent'].includes(s)) {
    acts.push({ key: 'send', tip: 'sales.quotation.send', perm: 'sales:quote:send' })
    acts.push({ key: 'feedback', tip: 'sales.quotation.feedback', perm: 'sales:quote:feedback' })
  }
  if (s === 'accepted' && !row.contractId) {
    acts.push({ key: 'toContract', tip: 'sales.quotation.toContract', perm: 'sales:quote:to-contract' })
  }
  acts.push({ key: 'print', tip: 'sales.quotation.print' })
  if (s === 'draft') acts.push({ key: 'delete', tip: 'common.action.delete', danger: true, perm: 'sales:quote:edit' })
  return acts
}

function onRowAction(key: string, row: Quotation) {
  if (key === 'detail') openDetail(row)
  else if (key === 'edit') router.push(`/sales/quotations/${row.id}/edit`)
  else if (key === 'submit') void doSubmit(row)
  else if (key === 'delete') void remove(row)
  else if (key === 'send') openSend(row)
  else if (key === 'feedback') openFeedback(row)
  else if (key === 'toContract') void doToContract(row)
  else if (key === 'print') openPrint(row)
}

// ---- 详情抽屉 ----
const detailVisible = ref(false)
const detailId = ref(0)

function openDetail(row: Quotation) {
  detailId.value = row.id
  detailVisible.value = true
}

function openPrint(row: Quotation) {
  window.open(`/sales/quotations/${row.id}/print`, '_blank')
}

async function doSubmit(row: Quotation) {
  try {
    await ElMessageBox.confirm(t('sales.quotation.submitConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await submitQuotation(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function remove(row: Quotation) {
  try {
    await ElMessageBox.confirm(t('sales.quotation.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteQuotation(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

// ---- 发送 ----
const sendVisible = ref(false)
const sendRow = ref<Quotation | null>(null)
const sendChannel = ref<'email' | 'print' | 'download'>('email')
const sendRecipient = ref('')
const sending = ref(false)

function openSend(row: Quotation) {
  sendRow.value = row
  sendChannel.value = row.contactEmail ? 'email' : 'print'
  sendRecipient.value = row.contactEmail || ''
  sendVisible.value = true
}

async function doSend() {
  if (!sendRow.value) return
  sending.value = true
  try {
    await sendQuotation(sendRow.value.id, sendChannel.value, sendRecipient.value.trim())
    ElMessage.success(t('common.message.saveSuccess'))
    sendVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    sending.value = false
  }
}

// ---- 客户反馈 ----
const fbVisible = ref(false)
const fbRow = ref<Quotation | null>(null)
const fbAction = ref<'accept' | 'decline'>('accept')
const fbNote = ref('')
const fbSaving = ref(false)

function openFeedback(row: Quotation) {
  fbRow.value = row
  fbAction.value = 'accept'
  fbNote.value = ''
  fbVisible.value = true
}

async function doFeedback() {
  if (!fbRow.value) return
  fbSaving.value = true
  try {
    await feedbackQuotation(fbRow.value.id, fbAction.value, fbNote.value.trim())
    ElMessage.success(t('common.message.saveSuccess'))
    fbVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    fbSaving.value = false
  }
}

async function doToContract(row: Quotation) {
  try {
    await ElMessageBox.confirm(t('sales.quotation.toContractConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    const r = await quotationToContract(row.id)
    ElMessage.success(t('sales.quotation.toContractDone'))
    list.refresh()
    router.push(`/contract/contracts/${r.contractId}/edit`)
  } catch {
    /* http notifies */
  }
}

function fmtAmount(row: Record<string, unknown>) {
  const n = Number(row.totalAmount ?? 0)
  return Number.isFinite(n) ? n.toLocaleString() : String(row.totalAmount ?? '-')
}
</script>

<template>
  <ListPage :title="t('sales.quotation.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'sales:quote:create'" type="primary" @click="router.push('/sales/quotations/new')">
        {{ t('sales.quotation.create') }}
      </el-button>
      <ExportButton v-permission="'sales:quote:list:export'" :export-fn="() => list.exportList()" />
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
        <template #totalAmount="{ row }">{{ fmtAmount(row) }}</template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="sales.quotation.status" />
        </template>
        <template #quoteNo="{ row }">
          <el-button v-if="row.quoteNo" link type="primary" @click="openDetail(row as unknown as Quotation)">
            {{ row.quoteNo }}
          </el-button>
          <span v-else>-</span>
        </template>
        <template #sentChannel="{ row }">
          {{ row.sentChannel ? t(`sales.quotation.channel${String(row.sentChannel).charAt(0).toUpperCase()}${String(row.sentChannel).slice(1)}`) : '-' }}
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="150" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar :actions="rowActions(row as unknown as Quotation)" @select="(k) => onRowAction(k, row as unknown as Quotation)" />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>

    <QuotationDetailDrawer v-model="detailVisible" :quotation-id="detailId" @changed="list.refresh()" />

    <el-dialog v-model="sendVisible" :title="t('sales.quotation.sendTitle')" width="var(--bs-layout-dialog-xs)">
      <el-form label-position="top">
        <el-form-item :label="t('sales.quotation.sendChannel')">
          <el-radio-group v-model="sendChannel">
            <el-radio-button value="email">{{ t('sales.quotation.channelEmail') }}</el-radio-button>
            <el-radio-button value="print">{{ t('sales.quotation.channelPrint') }}</el-radio-button>
            <el-radio-button value="download">{{ t('sales.quotation.channelDownload') }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item v-if="sendChannel === 'email'" :label="t('sales.quotation.sendRecipient')">
          <el-input v-model="sendRecipient" :placeholder="t('sales.quotation.sendRecipientPlaceholder')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="sendVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="sending" @click="doSend">{{ t('common.action.confirm') }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="fbVisible" :title="t('sales.quotation.feedbackTitle')" width="var(--bs-layout-dialog-xs)">
      <el-form label-position="top">
        <el-form-item>
          <el-radio-group v-model="fbAction">
            <el-radio-button value="accept">{{ t('sales.quotation.feedbackAccept') }}</el-radio-button>
            <el-radio-button value="decline">{{ t('sales.quotation.feedbackDecline') }}</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item :label="t('sales.quotation.feedbackNote')">
          <el-input v-model="fbNote" type="textarea" :rows="3" :placeholder="t('sales.quotation.feedbackNotePlaceholder')" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="fbVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="fbSaving" @click="doFeedback">{{ t('common.action.confirm') }}</el-button>
      </template>
    </el-dialog>
  </ListPage>
</template>
