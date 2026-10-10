<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import StatusTag from '@/components/common/StatusTag.vue'
import ApprovalTimeline from '@/components/approval/ApprovalTimeline.vue'
import { useDictOptions } from '@/composables/useDict'
import { getSettlement } from '@/api/finance'
import type { SettlementDetail } from '@/api/types'

defineOptions({ name: 'SettlementDetailDrawer' })

const props = defineProps<{
  modelValue: boolean
  settlementId: number | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
}>()

const { t } = useI18n()

const loading = ref(false)
const detail = ref<SettlementDetail | null>(null)

const payTypeOpts = useDictOptions('pay_type')

function payTypeLabel(value: unknown) {
  const v = String(value ?? '')
  return payTypeOpts.opts.value.find((x) => x.value === v)?.label || v || '-'
}

function fmtAmount(row: Record<string, unknown>, prop: string) {
  const n = Number(row[prop] ?? 0)
  return Number.isFinite(n) ? n.toLocaleString() : String(row[prop] ?? '-')
}

async function load() {
  if (!props.settlementId) return
  loading.value = true
  try {
    detail.value = await getSettlement(props.settlementId)
  } catch {
    detail.value = null
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.modelValue, props.settlementId],
  ([visible]) => {
    if (visible) {
      detail.value = null
      void load()
    }
  },
)

defineExpose({ reload: load })
</script>

<template>
  <el-drawer
    :model-value="props.modelValue"
    :title="t('finance.settlement.detail')"
    size="640px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="drawer-body">
      <template v-if="detail">
        <el-descriptions :column="2" border>
          <el-descriptions-item :label="t('finance.settlement.settlementNo')">{{ detail.settlementNo }}</el-descriptions-item>
          <el-descriptions-item :label="t('finance.settlement.taskNo')">{{ detail.taskNo }}</el-descriptions-item>
          <el-descriptions-item :label="t('finance.settlement.customerName')">{{ detail.customerName }}</el-descriptions-item>
          <el-descriptions-item :label="t('finance.settlement.contractNo')">{{ detail.contractNo || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('finance.settlement.amount')">
            {{ fmtAmount(detail as unknown as Record<string, unknown>, 'amount') }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('finance.settlement.invoiceableAmount')">
            {{ fmtAmount(detail as unknown as Record<string, unknown>, 'invoiceableAmount') }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('common.form.status')">
            <StatusTag :status="detail.status" i18n-prefix="finance.settlement.status" />
          </el-descriptions-item>
          <el-descriptions-item :label="t('finance.settlement.createBy')">{{ detail.createBy || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('finance.settlement.createTime')">{{ detail.createTime || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('finance.settlement.remark')">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <div class="section-title">{{ t('finance.settlement.invoices') }}</div>
        <el-table :data="detail.invoices ?? []" border size="small">
          <el-table-column prop="invoiceNo" :label="t('finance.settlement.invoiceNo')" min-width="140">
            <template #default="{ row }">{{ row.invoiceNo || '-' }}</template>
          </el-table-column>
          <el-table-column :label="t('finance.settlement.amount')" width="120">
            <template #default="{ row }">{{ fmtAmount(row, 'amount') }}</template>
          </el-table-column>
          <el-table-column prop="invoiceDate" :label="t('finance.settlement.invoiceDate')" width="120">
            <template #default="{ row }">{{ row.invoiceDate || '-' }}</template>
          </el-table-column>
          <el-table-column prop="status" :label="t('finance.settlement.invoiceStatus')" width="110">
            <template #default="{ row }">{{ row.status || '-' }}</template>
          </el-table-column>
        </el-table>

        <div class="section-title">{{ t('finance.settlement.payments') }}</div>
        <el-table :data="detail.payments ?? []" border size="small">
          <el-table-column prop="paymentNo" :label="t('finance.payment.paymentNo')" min-width="140" />
          <el-table-column :label="t('finance.payment.payType')" width="110">
            <template #default="{ row }">{{ payTypeLabel(row.payType) }}</template>
          </el-table-column>
          <el-table-column prop="payerName" :label="t('finance.payment.payerName')" min-width="120" />
          <el-table-column :label="t('finance.payment.amount')" width="120">
            <template #default="{ row }">{{ fmtAmount(row, 'amount') }}</template>
          </el-table-column>
          <el-table-column prop="bank" :label="t('finance.payment.bank')" min-width="120">
            <template #default="{ row }">{{ row.bank || '-' }}</template>
          </el-table-column>
          <el-table-column prop="paidAt" :label="t('finance.payment.paidAt')" width="110" />
        </el-table>

        <div class="section-title">{{ t('finance.settlement.invoiceTimeline') }}</div>
        <ApprovalTimeline :records="detail.timeline ?? []" />
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
.drawer-body {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.section-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}
</style>
