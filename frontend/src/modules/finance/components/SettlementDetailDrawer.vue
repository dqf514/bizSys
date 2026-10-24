<script setup lang="ts">
import { reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import StatusTag from '@/components/common/StatusTag.vue'
import ApprovalTimeline from '@/components/approval/ApprovalTimeline.vue'
import RemoteSelect, { type RemoteOption } from '@/components/form/RemoteSelect.vue'
import { useDictOptions } from '@/composables/useDict'
import { getSettlement, sendSettlementConfirm, confirmSettlement } from '@/api/finance'
import { userOptions } from '@/api/admin'
import type { SettlementDetail } from '@/api/types'

defineOptions({ name: 'SettlementDetailDrawer' })

const props = defineProps<{
  modelValue: boolean
  settlementId: number | null
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'changed'): void
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

/* ---------- 客户确认 ---------- */
async function fetchUsers(q: string): Promise<RemoteOption[]> {
  try {
    const opts = await userOptions(q)
    return (opts ?? []).map((o) => ({ id: o.id, label: o.label, sub: o.sub }))
  } catch {
    return []
  }
}

const sendVisible = ref(false)
const sendSaving = ref(false)
const sendForm = reactive({ receiverId: null as number | null, note: '' })

function openSend() {
  Object.assign(sendForm, { receiverId: null, note: '' })
  sendVisible.value = true
}

async function doSend() {
  if (!props.settlementId || !sendForm.receiverId) return
  sendSaving.value = true
  try {
    await sendSettlementConfirm(props.settlementId, {
      receiverId: sendForm.receiverId,
      note: sendForm.note || undefined,
    })
    ElMessage.success(t('common.message.submitSuccess'))
    sendVisible.value = false
    await load()
    emit('changed')
  } catch {
    /* http notifies */
  } finally {
    sendSaving.value = false
  }
}

const markVisible = ref(false)
const markSaving = ref(false)
const markForm = reactive({ action: 'confirm' as 'confirm' | 'object', note: '' })

function openMark(action: 'confirm' | 'object') {
  Object.assign(markForm, { action, note: '' })
  markVisible.value = true
}

async function doMark() {
  if (!props.settlementId) return
  markSaving.value = true
  try {
    await confirmSettlement(props.settlementId, { action: markForm.action, note: markForm.note })
    ElMessage.success(t('common.message.submitSuccess'))
    markVisible.value = false
    await load()
    emit('changed')
  } catch {
    /* http notifies */
  } finally {
    markSaving.value = false
  }
}
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
          <el-descriptions-item :label="t('finance.settlement.confirmStatusLabel')">
            <StatusTag
              v-if="detail.confirmStatus"
              :status="detail.confirmStatus"
              i18n-prefix="finance.settlement.confirmStatus"
            />
            <span v-else>{{ t('finance.settlement.notConfirmed') }}</span>
          </el-descriptions-item>
          <el-descriptions-item :label="t('finance.settlement.createBy')">{{ detail.createBy || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('finance.settlement.createTime')">{{ detail.createTime || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('finance.settlement.remark')">{{ detail.remark || '-' }}</el-descriptions-item>
        </el-descriptions>

        <template v-if="detail.status === 'pending'">
          <el-alert type="info" :closable="false" :title="t('finance.settlement.confirmHint')" />
          <div v-permission="'finance:settlement:confirm'" class="confirm-actions">
            <el-button
              v-if="!detail.confirmStatus || detail.confirmStatus === 'objected'"
              type="primary"
              @click="openSend"
            >
              {{ t('finance.settlement.sendConfirm') }}
            </el-button>
            <template v-if="detail.confirmStatus === 'pending'">
              <el-button type="success" @click="openMark('confirm')">{{ t('finance.settlement.markConfirmed') }}</el-button>
              <el-button type="danger" plain @click="openMark('object')">{{ t('finance.settlement.markObjected') }}</el-button>
            </template>
          </div>
        </template>

        <template v-if="detail.confirmRecords?.length">
          <div class="section-title">{{ t('finance.settlement.confirmRecords') }}</div>
          <el-table :data="detail.confirmRecords" border size="small">
            <el-table-column prop="action" :label="t('common.form.status')" width="100" sortable>
              <template #default="{ row }">
                <StatusTag :status="row.action" i18n-prefix="finance.settlement.confirmAction" />
              </template>
            </el-table-column>
            <el-table-column prop="operatorName" :label="t('finance.settlement.confirmOperator')" width="100" sortable />
            <el-table-column prop="receiverName" :label="t('finance.settlement.confirmReceiver')" width="100" sortable>
              <template #default="{ row }">{{ row.receiverName || '-' }}</template>
            </el-table-column>
            <el-table-column prop="note" :label="t('finance.settlement.confirmNote')" min-width="140">
              <template #default="{ row }">{{ row.note || '-' }}</template>
            </el-table-column>
            <el-table-column prop="createTime" :label="t('finance.settlement.createTime')" width="160" sortable />
          </el-table>
        </template>

        <div class="section-title">{{ t('finance.settlement.invoices') }}</div>
        <el-table :data="detail.invoices ?? []" border size="small">
          <el-table-column prop="invoiceNo" :label="t('finance.settlement.invoiceNo')" min-width="140" sortable>
            <template #default="{ row }">{{ row.invoiceNo || '-' }}</template>
          </el-table-column>
          <el-table-column prop="amount" :label="t('finance.settlement.amount')" width="120" sortable align="right">
            <template #default="{ row }">{{ fmtAmount(row, 'amount') }}</template>
          </el-table-column>
          <el-table-column prop="invoiceDate" :label="t('finance.settlement.invoiceDate')" width="120" sortable>
            <template #default="{ row }">{{ row.invoiceDate || '-' }}</template>
          </el-table-column>
          <el-table-column prop="status" :label="t('finance.settlement.invoiceStatus')" width="110" sortable>
            <template #default="{ row }">{{ row.status || '-' }}</template>
          </el-table-column>
        </el-table>

        <div class="section-title">{{ t('finance.settlement.payments') }}</div>
        <el-table :data="detail.payments ?? []" border size="small">
          <el-table-column prop="paymentNo" :label="t('finance.payment.paymentNo')" min-width="140" sortable />
          <el-table-column prop="payType" :label="t('finance.payment.payType')" width="110" sortable>
            <template #default="{ row }">{{ payTypeLabel(row.payType) }}</template>
          </el-table-column>
          <el-table-column prop="payerName" :label="t('finance.payment.payerName')" min-width="120" sortable />
          <el-table-column prop="amount" :label="t('finance.payment.amount')" width="120" sortable align="right">
            <template #default="{ row }">{{ fmtAmount(row, 'amount') }}</template>
          </el-table-column>
          <el-table-column prop="bank" :label="t('finance.payment.bank')" min-width="120">
            <template #default="{ row }">{{ row.bank || '-' }}</template>
          </el-table-column>
          <el-table-column prop="paidAt" :label="t('finance.payment.paidAt')" width="110" sortable />
        </el-table>

        <div class="section-title">{{ t('finance.settlement.invoiceTimeline') }}</div>
        <ApprovalTimeline :records="detail.timeline ?? []" />
      </template>
    </div>

    <el-dialog v-model="sendVisible" :title="t('finance.settlement.sendConfirm')" width="480px" append-to-body>
      <el-form label-width="90px">
        <el-form-item :label="t('finance.settlement.confirmReceiver')" required>
          <RemoteSelect v-model="sendForm.receiverId" :fetch="fetchUsers" />
        </el-form-item>
        <el-form-item :label="t('finance.settlement.confirmNote')">
          <el-input v-model="sendForm.note" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="sendVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :disabled="!sendForm.receiverId" :loading="sendSaving" @click="doSend">
          {{ t('common.action.submit') }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="markVisible"
      :title="markForm.action === 'confirm' ? t('finance.settlement.markConfirmed') : t('finance.settlement.markObjected')"
      width="480px"
      append-to-body
    >
      <el-form label-width="90px">
        <el-form-item :label="t('finance.settlement.confirmNote')">
          <el-input
            v-model="markForm.note"
            type="textarea"
            :rows="2"
            :placeholder="t('finance.settlement.confirmNotePlaceholder')"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="markVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="markSaving" @click="doMark">{{ t('common.action.submit') }}</el-button>
      </template>
    </el-dialog>
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

.confirm-actions {
  display: flex;
  gap: var(--bs-space-2);
}
</style>
