<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import StatusTag from '@/components/common/StatusTag.vue'
import SettlementDetailDrawer from '@/modules/finance/components/SettlementDetailDrawer.vue'
import { useDictOptions } from '@/composables/useDict'
import { getCustomer } from '@/api/crm'
import { listContracts } from '@/api/contract'
import { listTasks } from '@/api/task'
import { listSettlements } from '@/api/finance'
import type { Contract, CustomerDetail, Settlement, Task } from '@/api/types'

defineOptions({ name: 'CustomerDetailDrawer' })

const props = defineProps<{
  modelValue: boolean
  customerId: number | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
}>()

const { t } = useI18n()
const router = useRouter()

const loading = ref(false)
const detail = ref<CustomerDetail | null>(null)

const typeOpts = useDictOptions('customer_type')
const gradeOpts = useDictOptions('customer_grade')

function typeLabel(value: unknown) {
  const v = String(value ?? '')
  return typeOpts.opts.value.find((x) => x.value === v)?.label || v || '-'
}

function gradeLabel(value: unknown) {
  const v = String(value ?? '')
  return gradeOpts.opts.value.find((x) => x.value === v)?.label || v || '-'
}

function fmtMoney(v: number | string | undefined | null) {
  const n = Number(v ?? 0)
  return Number.isFinite(n) ? n.toLocaleString() : String(v ?? '-')
}

async function load() {
  if (!props.customerId) return
  loading.value = true
  try {
    detail.value = await getCustomer(props.customerId)
  } catch {
    detail.value = null
  } finally {
    loading.value = false
  }
}

/* ---------- related records (lazy per tab) ---------- */
const activeTab = ref('contracts')
const contracts = ref<Contract[]>([])
const tasks = ref<Task[]>([])
const settlements = ref<Settlement[]>([])
const relatedLoading = ref(false)
const loadedTabs = new Set<string>()

async function loadRelated(tab: string) {
  if (!props.customerId || loadedTabs.has(tab)) return
  loadedTabs.add(tab)
  relatedLoading.value = true
  try {
    if (tab === 'contracts') {
      const data = await listContracts({ page: 1, size: 100, filters: { customer_id: props.customerId } })
      contracts.value = data.items ?? []
    } else if (tab === 'tasks') {
      const data = await listTasks({ page: 1, size: 100, filters: { customer_id: props.customerId } })
      tasks.value = data.items ?? []
    } else if (tab === 'settlements') {
      const data = await listSettlements({ page: 1, size: 100, filters: { customer_id: props.customerId } })
      settlements.value = data.items ?? []
    }
  } catch {
    /* keep empty */
  } finally {
    relatedLoading.value = false
  }
}

watch(activeTab, (tab) => void loadRelated(tab))

watch(
  () => [props.modelValue, props.customerId],
  ([visible]) => {
    if (visible) {
      detail.value = null
      contracts.value = []
      tasks.value = []
      settlements.value = []
      loadedTabs.clear()
      activeTab.value = 'contracts'
      void load()
      void loadRelated('contracts')
    }
  },
)

const settleDrawerVisible = ref(false)
const settleDrawerId = ref<number | null>(null)

function openContract(row: Contract) {
  router.push(`/contract/contracts/${row.id}`)
}

function openTask(row: Task) {
  router.push(`/task/tasks/${row.id}`)
}

function openSettlement(row: Settlement) {
  settleDrawerId.value = row.id
  settleDrawerVisible.value = true
}
</script>

<template>
  <el-drawer
    :model-value="props.modelValue"
    size="720px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <template #header>
      <div class="drawer-header">
        <span class="drawer-title">{{ detail?.name || t('crm.customer.detail') }}</span>
        <template v-if="detail">
          <el-tag size="small" effect="plain">{{ gradeLabel(detail.grade) }}</el-tag>
          <StatusTag :status="detail.status" i18n-prefix="common.status" />
        </template>
      </div>
    </template>

    <div v-loading="loading" class="drawer-body">
      <template v-if="detail">
        <div class="section-title">{{ t('crm.detail.basicInfo') }}</div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item :label="t('crm.customer.customerNo')">{{ detail.customerNo }}</el-descriptions-item>
          <el-descriptions-item :label="t('crm.customer.customerType')">{{ typeLabel(detail.customerType) }}</el-descriptions-item>
          <el-descriptions-item :label="t('crm.customer.contactPerson')">{{ detail.contactPerson || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('crm.customer.contactPhone')">{{ detail.contactPhone || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('crm.customer.taxNo')">{{ detail.taxNo || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('crm.customer.payOrg')">{{ detail.payOrg || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('crm.customer.bankName')">{{ detail.bankName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('crm.customer.bankAccount')">{{ detail.bankAccount || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('crm.customer.address')" :span="2">
            {{ [detail.country, detail.province, detail.city, detail.address].filter(Boolean).join(' ') || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('crm.customer.remark')" :span="2">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div v-if="detail.summary" class="stat-strip">
          <div class="stat-card">
            <div class="stat-label">{{ t('crm.detail.contractCount') }}</div>
            <div class="stat-value">{{ detail.summary.contractCount }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">{{ t('crm.detail.contractTotal') }}</div>
            <div class="stat-value">{{ fmtMoney(detail.summary.contractTotal) }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">{{ t('crm.detail.taskCount') }}</div>
            <div class="stat-value">{{ detail.summary.taskCount }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">{{ t('crm.detail.settledTotal') }}</div>
            <div class="stat-value">{{ fmtMoney(detail.summary.settledTotal) }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">{{ t('crm.detail.paidTotal') }}</div>
            <div class="stat-value stat-paid">{{ fmtMoney(detail.summary.paidTotal) }}</div>
          </div>
        </div>

        <el-tabs v-model="activeTab">
          <el-tab-pane :label="t('crm.detail.contracts')" name="contracts">
            <el-table v-loading="relatedLoading" :data="contracts" border stripe size="small">
              <el-table-column :label="t('contract.contract.contractNo')" width="150">
                <template #default="{ row }">
                  <el-button link type="primary" @click="openContract(row as unknown as Contract)">
                    {{ row.contractNo }}
                  </el-button>
                </template>
              </el-table-column>
              <el-table-column :label="t('contract.contract.name')" prop="name" min-width="160" />
              <el-table-column :label="t('contract.contract.amount')" width="120">
                <template #default="{ row }">{{ fmtMoney(row.amount) }}</template>
              </el-table-column>
              <el-table-column :label="t('common.form.status')" width="110">
                <template #default="{ row }">
                  <StatusTag :status="String(row.status)" i18n-prefix="contract.contract.status" />
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane :label="t('crm.detail.tasks')" name="tasks">
            <el-table v-loading="relatedLoading" :data="tasks" border stripe size="small">
              <el-table-column :label="t('task.task.taskNo')" width="150">
                <template #default="{ row }">
                  <el-button link type="primary" @click="openTask(row as unknown as Task)">
                    {{ row.taskNo }}
                  </el-button>
                </template>
              </el-table-column>
              <el-table-column :label="t('task.task.taskName')" prop="taskName" min-width="160" />
              <el-table-column :label="t('common.form.status')" width="110">
                <template #default="{ row }">
                  <StatusTag :status="String(row.status)" i18n-prefix="task.task.status" />
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>

          <el-tab-pane :label="t('crm.detail.settlements')" name="settlements">
            <el-table v-loading="relatedLoading" :data="settlements" border stripe size="small">
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
              <el-table-column :label="t('common.form.status')" width="110">
                <template #default="{ row }">
                  <StatusTag :status="String(row.status)" i18n-prefix="finance.settlement.status" />
                </template>
              </el-table-column>
            </el-table>
          </el-tab-pane>
        </el-tabs>
      </template>
    </div>

    <SettlementDetailDrawer v-model="settleDrawerVisible" :settlement-id="settleDrawerId" />
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

.stat-strip {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--bs-space-2);
}

.stat-card {
  padding: var(--bs-space-2) var(--bs-space-3);
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
  font-size: var(--bs-typography-font-size-xl);
  font-weight: 700;
  line-height: 1.2;
}

.stat-paid {
  color: var(--bs-color-semantic-success);
}
</style>
