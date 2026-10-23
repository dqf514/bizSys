<script setup lang="ts">
import { computed, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import StatusTag from '@/components/common/StatusTag.vue'
import CountUp from '@/components/common/CountUp.vue'
import ApprovalTimeline from '@/components/approval/ApprovalTimeline.vue'
import SettlementDetailDrawer from '@/modules/finance/components/SettlementDetailDrawer.vue'
import { getContract, getContractFinanceSummary, downloadAttachment, voidContract } from '@/api/contract'
import { getCustomer } from '@/api/crm'
import { getTimeline } from '@/api/approval'
import { listTasks } from '@/api/task'
import { listReports } from '@/api/report'
import { listSettlements, listInvoices, listPayments } from '@/api/finance'
import { useDictOptions } from '@/composables/useDict'
import { useContextStore, type ContextSection } from '@/stores/context'
import type {
  Attachment,
  Contract,
  ContractFinanceSummary,
  CustomerDetail,
  InvoiceListItem,
  Payment,
  Report,
  Settlement,
  Task,
  TimelineRecord,
} from '@/api/types'

defineOptions({ name: 'ContractDetail' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const context = useContextStore()

const detail = ref<Contract | null>(null)
const customerDetail = ref<CustomerDetail | null>(null)
const attachments = ref<Attachment[]>([])
// 附件分组：合同电子版在上，其他附件在下
const attachmentGroups = computed(() =>
  (['econtract', 'other'] as const)
    .map((cat) => ({
      category: cat,
      label: t(cat === 'econtract' ? 'contract.contract.attCatEcontract' : 'contract.contract.attCatOther'),
      files: attachments.value.filter((a) => (a.category === 'econtract' ? 'econtract' : 'other') === cat),
    }))
    .filter((g) => g.files.length > 0),
)
const records = ref<TimelineRecord[]>([])
const loading = ref(false)
const timelineLoading = ref(false)
const activeTab = ref('basic')

/* ---------- 任务与报告（页签首次激活时加载） ---------- */
const tasks = ref<Task[]>([])
const reports = ref<Report[]>([])
const tasksTotal = ref(0)
const tasksLoading = ref(false)
const reportsLoading = ref(false)
let tasksReportsLoaded = false

async function loadTasksReports() {
  const id = Number(route.params.id)
  if (!id) return
  tasksLoading.value = true
  reportsLoading.value = true
  try {
    const data = await listTasks({ page: 1, size: 100, filters: { contract_id: id } })
    tasks.value = data.items ?? []
    tasksTotal.value = data.total ?? tasks.value.length
  } catch {
    tasks.value = []
  } finally {
    tasksLoading.value = false
  }
  try {
    const data = await listReports({ page: 1, size: 100, filters: { contract_id: id } })
    reports.value = data.items ?? []
  } catch {
    reports.value = []
  } finally {
    reportsLoading.value = false
  }
}

watch(activeTab, (tab) => {
  if (tab === 'tasksReports' && !tasksReportsLoaded) {
    tasksReportsLoaded = true
    void loadTasksReports()
  }
  if (tab === 'finance' && !financeLoaded) {
    financeLoaded = true
    void loadFinance()
  }
})

// 任务数徽标：任务与报告页签是懒加载的，打开页面前先用一次轻量 count 查询
async function loadTaskCount(id: number) {
  try {
    const data = await listTasks({ page: 1, size: 1, filters: { contract_id: id } })
    tasksTotal.value = data.total ?? 0
  } catch {
    tasksTotal.value = 0
  }
}

function openTask(row: Task) {
  router.push(`/task/tasks/${row.id}`)
}

/* ---------- 财务信息 ---------- */
const financeSummary = ref<ContractFinanceSummary | null>(null)
const settlements = ref<Settlement[]>([])
const invoices = ref<InvoiceListItem[]>([])
const payments = ref<Payment[]>([])
const financeLoading = ref(false)
let financeLoaded = false

const settleDrawerVisible = ref(false)
const settleDrawerId = ref<number | null>(null)

const payTypeOpts = useDictOptions('pay_type')
const typeOpts = useDictOptions('contract_type')
const payCycleOpts = useDictOptions('pay_cycle')
const deliveryOpts = useDictOptions('delivery_way')

function payTypeLabel(value: unknown) {
  const v = String(value ?? '')
  return payTypeOpts.opts.value.find((x) => x.value === v)?.label || v || '-'
}

function dictLabel(list: { label: string; value: string }[], value: unknown) {
  const v = String(value ?? '')
  if (!v) return '-'
  return list.find((x) => x.value === v)?.label || v
}

function fmtMoney(v: number | string | undefined | null) {
  const n = Number(v ?? 0)
  return Number.isFinite(n) ? n.toLocaleString() : String(v ?? '-')
}

function toNum(v: number | string | undefined | null) {
  const n = Number(v ?? 0)
  return Number.isFinite(n) ? n : 0
}

const outstandingValue = computed(() => {
  const fs = financeSummary.value
  if (!fs) return 0
  return toNum(fs.contractAmount) - toNum(fs.paidTotal)
})

// 财务页签徽标：结算+发票+回款笔数之和，复用已预加载的 finance-summary
const financeCount = computed(() => {
  const fs = financeSummary.value
  if (!fs) return 0
  return toNum(fs.settlementCount) + toNum(fs.invoiceCount) + toNum(fs.paymentCount)
})

function outstanding() {
  if (!financeSummary.value) return '-'
  return fmtMoney(Number(financeSummary.value.contractAmount ?? 0) - Number(financeSummary.value.paidTotal ?? 0))
}

/* ---------- 关联面板 ---------- */
function publishContext() {
  const d = detail.value
  if (!d) return
  const sections: ContextSection[] = []
  const cust = customerDetail.value
  sections.push({
    key: 'customer',
    title: 'common.context.customer',
    type: 'fields',
    items: [
      { label: 'crm.customer.name', value: cust?.name || d.customerName },
      { label: 'crm.customer.grade', value: cust?.grade || '-' },
      { label: 'crm.customer.contactPerson', value: cust?.contactPerson || d.contactPerson || '-' },
      { label: 'crm.customer.contactPhone', value: cust?.contactPhone || d.contactPhone || '-' },
    ],
  })
  const fs = financeSummary.value
  if (fs) {
    sections.push({
      key: 'finance',
      title: 'common.context.financeOverview',
      type: 'stats',
      items: [
        { label: 'contract.finance.settledTotal', value: fmtMoney(fs.settledTotal) },
        { label: 'contract.finance.invoicedTotal', value: fmtMoney(fs.invoicedTotal) },
        { label: 'contract.finance.paidTotal', value: fmtMoney(fs.paidTotal) },
        { label: 'contract.finance.outstanding', value: outstanding(), emphasize: true },
      ],
    })
  }
  sections.push({
    key: 'links',
    title: 'common.context.quickLinks',
    type: 'links',
    items: [
      ...(d.customerId
        ? [{ label: cust?.name || d.customerName, to: `/crm/customers?detail=${d.customerId}` }]
        : []),
      { label: 'common.context.newTask', to: '/task/tasks/new' },
      { label: 'common.context.settlements', to: '/finance/settlements' },
    ],
  })
  context.publish({ title: d.name, subtitle: d.contractNo, recordKey: `contract:${d.id}`, sections })
}

async function loadFinanceSummary(id: number) {
  try {
    financeSummary.value = await getContractFinanceSummary(id)
  } catch {
    financeSummary.value = null
  }
  publishContext()
}

async function loadFinance() {
  const id = Number(route.params.id)
  if (!id) return
  financeLoading.value = true
  try {
    const [s, i, p] = await Promise.all([
      listSettlements({ page: 1, size: 100, filters: { contract_id: id } }),
      listInvoices({ page: 1, size: 100, filters: { contract_id: id } }),
      listPayments({ page: 1, size: 100, filters: { contract_id: id } }),
    ])
    settlements.value = s.items ?? []
    invoices.value = i.items ?? []
    payments.value = p.items ?? []
  } catch {
    settlements.value = []
    invoices.value = []
    payments.value = []
  } finally {
    financeLoading.value = false
  }
}

function openSettlement(row: Settlement) {
  settleDrawerId.value = row.id
  settleDrawerVisible.value = true
}

async function load() {
  const id = Number(route.params.id)
  if (!id) return
  loading.value = true
  try {
    const data = await getContract(id)
    detail.value = data
    attachments.value = data.attachments ?? []
    void loadFinanceSummary(id)
    void loadTaskCount(id)
    customerDetail.value = null
    if (data.customerId) {
      getCustomer(data.customerId)
        .then((c) => {
          customerDetail.value = c
          publishContext()
        })
        .catch(() => {
          /* customer section falls back to contract fields */
        })
    }
    publishContext()
    if (data.flowInstanceId || data.status === 'approving' || data.status === 'approved') {
      timelineLoading.value = true
      try {
        const tl = await getTimeline('contract', id)
        records.value = tl.records ?? []
      } catch {
        records.value = []
      } finally {
        timelineLoading.value = false
      }
    }
  } catch {
    detail.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

// keep-alive page: re-publish when the tab becomes active again, clear when leaving
onActivated(() => {
  if (detail.value) publishContext()
})
onDeactivated(() => context.clear())
onUnmounted(() => context.clear())

async function doVoid() {
  if (!detail.value) return
  try {
    await ElMessageBox.confirm(t('contract.contract.voidConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await voidContract(detail.value.id)
    ElMessage.success(t('common.message.submitSuccess'))
    void load()
  } catch {
    /* http notifies */
  }
}
</script>

<template>
  <div class="contract-detail" v-loading="loading">
    <div class="detail-header">
      <h2 class="detail-title">
        {{ detail?.name || t('contract.contract.detail') }}
        <StatusTag v-if="detail" :status="detail.status" i18n-prefix="contract.contract.status" />
      </h2>
      <div class="header-actions">
        <el-button
          v-if="detail && ['draft', 'rejected', 'approved'].includes(detail.status)"
          v-permission="'contract:edit'"
          type="danger"
          plain
          @click="doVoid"
        >
          {{ t('contract.contract.void') }}
        </el-button>
        <el-button @click="router.push('/contract/contracts')">{{ t('common.action.back') }}</el-button>
      </div>
    </div>

    <div v-if="financeSummary" class="finance-strip bs-stagger">
      <div class="stat-card">
        <div class="stat-label">{{ t('contract.finance.contractAmount') }}</div>
        <div class="stat-value"><CountUp :value="toNum(financeSummary.contractAmount)" /></div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('contract.finance.settledTotal') }}</div>
        <div class="stat-value"><CountUp :value="toNum(financeSummary.settledTotal)" /></div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('contract.finance.invoicedTotal') }}</div>
        <div class="stat-value"><CountUp :value="toNum(financeSummary.invoicedTotal)" /></div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('contract.finance.paidTotal') }}</div>
        <div class="stat-value stat-paid"><CountUp :value="toNum(financeSummary.paidTotal)" /></div>
      </div>
      <div class="stat-card">
        <div class="stat-label">{{ t('contract.finance.outstanding') }}</div>
        <div class="stat-value stat-outstanding"><CountUp :value="outstandingValue" /></div>
      </div>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane :label="t('contract.contract.tabBasic')" name="basic">
        <el-descriptions v-if="detail" :column="2" border>
          <el-descriptions-item :label="t('contract.contract.contractNo')">{{ detail.contractNo }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.name')">{{ detail.name }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.customerName')">{{ detail.customerName }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.contractType')">{{ dictLabel(typeOpts.opts.value, detail.contractType) }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.amount')">{{ detail.amount }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.subjectType')">{{ detail.subjectType || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.startDate')">{{ detail.startDate }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.endDate')">{{ detail.endDate }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.payCycle')">{{ dictLabel(payCycleOpts.opts.value, detail.payCycle) }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.delivery')">{{ dictLabel(deliveryOpts.opts.value, detail.delivery) }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.sealType')">{{ detail.sealType || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.handlerName')">{{ detail.handlerName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.frameworkNo')">{{ detail.frameworkNo || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.paymentOrg')">{{ detail.paymentOrg || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.contactPerson')">{{ detail.contactPerson || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.contactPhone')">{{ detail.contactPhone || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('contract.contract.remark')" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>
      </el-tab-pane>

      <el-tab-pane name="attachments">
        <template #label>
          {{ t('contract.contract.tabAttachments') }}
          <span v-if="attachments.length" class="bs-tab-count">({{ attachments.length }})</span>
        </template>
        <div class="file-list">
          <div v-for="g in attachmentGroups" :key="g.category" class="att-group">
            <div class="att-group-title">{{ g.label }}</div>
            <div v-for="f in g.files" :key="String(f.id)" class="file-row">
              <el-tag size="small" :type="g.category === 'econtract' ? 'primary' : 'info'" effect="plain">
                {{ g.label }}
              </el-tag>
              <span>{{ f.fileName }}</span>
              <el-button link type="primary" @click="downloadAttachment(f.id, f.fileName)">
                {{ t('common.action.download') }}
              </el-button>
            </div>
          </div>
          <el-empty v-if="!attachments.length" :description="t('common.table.empty')" :image-size="60" />
        </div>
      </el-tab-pane>

      <el-tab-pane name="timeline">
        <template #label>
          {{ t('contract.contract.tabTimeline') }}
          <span v-if="records.length" class="bs-tab-count">({{ records.length }})</span>
        </template>
        <ApprovalTimeline :records="records" :loading="timelineLoading" />
      </el-tab-pane>

      <el-tab-pane name="tasksReports">
        <template #label>
          {{ t('contract.contract.tabTasksReports') }}
          <span v-if="tasksTotal" class="bs-tab-count">({{ tasksTotal }})</span>
        </template>
        <div class="tasks-reports">
          <div class="section-title">{{ t('contract.contract.relatedTasks') }}</div>
          <el-table v-loading="tasksLoading" :data="tasks" border stripe size="small">
            <el-table-column :label="t('task.task.taskNo')" width="150">
              <template #default="{ row }">
                <el-button link type="primary" @click="openTask(row as unknown as Task)">{{ row.taskNo }}</el-button>
              </template>
            </el-table-column>
            <el-table-column :label="t('task.task.taskName')" prop="taskName" min-width="160" />
            <el-table-column :label="t('common.form.status')" width="110">
              <template #default="{ row }">
                <StatusTag :status="String(row.status)" i18n-prefix="task.task.status" />
              </template>
            </el-table-column>
            <el-table-column :label="t('task.task.createTime')" prop="createTime" width="160" />
          </el-table>

          <div class="section-title">{{ t('contract.contract.relatedReports') }}</div>
          <el-table v-loading="reportsLoading" :data="reports" border stripe size="small">
            <el-table-column :label="t('report.report.reportNo')" prop="reportNo" width="150" />
            <el-table-column :label="t('report.report.taskNo')" prop="taskNo" width="140" />
            <el-table-column :label="t('report.report.itemName')" prop="itemName" min-width="130" />
            <el-table-column :label="t('common.form.status')" width="110">
              <template #default="{ row }">
                <StatusTag :status="String(row.status)" i18n-prefix="report.report.status" />
              </template>
            </el-table-column>
            <el-table-column :label="t('report.report.createTime')" prop="createTime" width="160" />
          </el-table>
        </div>
      </el-tab-pane>
      <el-tab-pane name="finance">
        <template #label>
          {{ t('contract.contract.tabFinance') }}
          <span v-if="financeCount" class="bs-tab-count">({{ financeCount }})</span>
        </template>
        <div v-loading="financeLoading" class="finance-tables">
          <div class="section-title">{{ t('contract.finance.settlements') }}</div>
          <el-table :data="settlements" border stripe size="small">
            <el-table-column :label="t('finance.settlement.settlementNo')" width="150">
              <template #default="{ row }">
                <el-button link type="primary" @click="openSettlement(row as unknown as Settlement)">
                  {{ row.settlementNo }}
                </el-button>
              </template>
            </el-table-column>
            <el-table-column :label="t('finance.settlement.amount')" width="120">
              <template #default="{ row }">{{ fmtMoney(row.amount) }}</template>
            </el-table-column>
            <el-table-column :label="t('finance.settlement.invoiceableAmount')" width="120">
              <template #default="{ row }">{{ fmtMoney(row.invoiceableAmount) }}</template>
            </el-table-column>
            <el-table-column :label="t('common.form.status')" width="110">
              <template #default="{ row }">
                <StatusTag :status="String(row.status)" i18n-prefix="finance.settlement.status" />
              </template>
            </el-table-column>
            <el-table-column :label="t('finance.settlement.createTime')" prop="createTime" width="160" />
          </el-table>

          <div class="section-title">{{ t('contract.finance.invoices') }}</div>
          <el-table :data="invoices" border stripe size="small">
            <el-table-column :label="t('finance.invoice.invoiceNo')" prop="invoiceNo" width="160">
              <template #default="{ row }">{{ row.invoiceNo || '-' }}</template>
            </el-table-column>
            <el-table-column :label="t('finance.invoice.settlementNo')" prop="settlementNo" width="150" />
            <el-table-column :label="t('finance.invoice.amount')" width="120">
              <template #default="{ row }">{{ fmtMoney(row.amount) }}</template>
            </el-table-column>
            <el-table-column :label="t('finance.invoice.invoiceDate')" width="120">
              <template #default="{ row }">{{ row.invoiceDate || '-' }}</template>
            </el-table-column>
            <el-table-column :label="t('common.form.status')" width="110">
              <template #default="{ row }">
                <StatusTag :status="String(row.status)" i18n-prefix="finance.invoice.status" />
              </template>
            </el-table-column>
          </el-table>

          <div class="section-title">{{ t('contract.finance.payments') }}</div>
          <el-table :data="payments" border stripe size="small">
            <el-table-column :label="t('finance.payment.paymentNo')" prop="paymentNo" width="160" />
            <el-table-column :label="t('finance.payment.payerName')" prop="payerName" min-width="140" />
            <el-table-column :label="t('finance.payment.amount')" width="120">
              <template #default="{ row }">{{ fmtMoney(row.amount) }}</template>
            </el-table-column>
            <el-table-column :label="t('finance.payment.payType')" width="110">
              <template #default="{ row }">{{ payTypeLabel(row.payType) }}</template>
            </el-table-column>
            <el-table-column :label="t('finance.payment.paidAt')" prop="paidAt" width="120" />
          </el-table>
        </div>
      </el-tab-pane>
    </el-tabs>

    <SettlementDetailDrawer v-model="settleDrawerVisible" :settlement-id="settleDrawerId" />
  </div>
</template>

<style scoped>
.contract-detail {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
  padding: var(--bs-space-4);
  height: 100%;
  overflow: auto;
  background: var(--bs-color-bg-surface);
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.detail-title {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.att-group {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.att-group-title {
  font-size: var(--bs-typography-font-size-sm);
  font-weight: 600;
  color: var(--bs-color-fg-muted);
}

.file-row {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  padding: 8px 12px;
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-sm);
}

.file-row .el-button {
  margin-left: auto;
}

.tasks-reports {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.section-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.finance-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--bs-space-3);
}

.stat-card {
  padding: var(--bs-space-3) var(--bs-space-4);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-app);
}

.stat-label {
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-secondary);
}

.stat-value {
  margin-top: var(--bs-space-1);
  font-size: var(--bs-typography-font-size-xxl);
  font-weight: 700;
  line-height: 1.2;
}

.stat-paid {
  color: var(--bs-color-semantic-success);
}

.stat-outstanding {
  color: var(--bs-color-semantic-warning);
}

.finance-tables {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}
</style>
