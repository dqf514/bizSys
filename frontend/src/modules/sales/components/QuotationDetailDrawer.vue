<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import StatusTag from '@/components/common/StatusTag.vue'
import ApprovalTimeline from '@/components/approval/ApprovalTimeline.vue'
import { getQuotation, quotationToContract } from '@/api/sales'
import type { Quotation } from '@/api/types'
import QuotationPreview from './QuotationPreview.vue'

defineOptions({ name: 'QuotationDetailDrawer' })

const props = defineProps<{
  modelValue: boolean
  quotationId: number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'changed'): void
}>()

const { t } = useI18n()
const router = useRouter()

const loading = ref(false)
const detail = ref<Quotation | null>(null)
const activeTab = ref('preview')

async function load() {
  if (!props.quotationId) return
  loading.value = true
  try {
    detail.value = await getQuotation(props.quotationId)
  } catch {
    detail.value = null
  } finally {
    loading.value = false
  }
}

watch(
  () => [props.modelValue, props.quotationId],
  ([v]) => {
    if (v) {
      activeTab.value = 'preview'
      void load()
    }
  },
)

function openContract() {
  if (detail.value?.contractId) router.push(`/contract/contracts/${detail.value.contractId}`)
}

async function doToContract() {
  if (!detail.value) return
  try {
    const r = await quotationToContract(detail.value.id)
    ElMessage.success(t('sales.quotation.toContractDone'))
    emit('changed')
    router.push(`/contract/contracts/${r.contractId}/edit`)
  } catch {
    /* http notifies */
  }
}

function channelLabel(ch: string) {
  if (!ch) return '-'
  return t(`sales.quotation.channel${ch.charAt(0).toUpperCase()}${ch.slice(1)}`)
}

function resultLabel(r: string) {
  if (!r) return '-'
  return t(`sales.quotation.result${r.charAt(0).toUpperCase()}${r.slice(1)}`)
}

/** aiMeta JSON 解析容错：坏数据不炸模板渲染 */
const aiSource = computed(() => {
  const raw = detail.value?.aiMeta
  if (!raw) return ''
  try {
    const src = JSON.parse(raw)?.source
    if (src === 'ai') return t('sales.quotation.aiSourceAi')
    if (src === 'history') return t('sales.quotation.aiSourceHistory')
    if (src === 'template') return t('sales.quotation.aiSourceTemplate')
  } catch {
    /* ignore bad meta */
  }
  return ''
})
</script>

<template>
  <el-drawer
    :model-value="modelValue"
    :title="detail ? `${detail.quoteNo || ''} ${detail.title}`.trim() : t('sales.quotation.detail')"
    size="720px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <div v-loading="loading" class="quote-detail">
      <template v-if="detail">
        <div class="qd-head">
          <StatusTag :status="detail.status" i18n-prefix="sales.quotation.status" />
          <el-tag v-if="aiSource" size="small" effect="plain">{{ aiSource }}</el-tag>
          <span class="qd-customer">{{ detail.customerName }}</span>
          <span class="qd-amount">{{ detail.currency }} {{ Number(detail.totalAmount).toLocaleString() }}</span>
        </div>

        <el-tabs v-model="activeTab">
          <el-tab-pane :label="t('sales.quotation.preview')" name="preview">
            <QuotationPreview
              :layout="detail.layout"
              :quote-no="detail.quoteNo"
              :customer-name="detail.customerName"
              :contact-name="detail.contactName"
              :contact-phone="detail.contactPhone"
              :valid-until="detail.validUntil"
              :items="detail.items"
              :tax-rate="detail.taxRate"
              :currency="detail.currency"
            />
          </el-tab-pane>
          <el-tab-pane :label="t('sales.quotation.timeline')" name="timeline">
            <ApprovalTimeline :records="detail.timeline ?? []" :loading="false" />
          </el-tab-pane>
          <el-tab-pane :label="t('sales.quotation.sendLogs')" name="sendLogs">
            <el-table :data="detail.sendLogs ?? []" size="small">
              <el-table-column prop="sentAt" :label="t('sales.quotation.sentAt')" width="150" />
              <el-table-column :label="t('sales.quotation.sentChannel')" width="110">
                <template #default="{ row }">{{ channelLabel(row.channel) }}</template>
              </el-table-column>
              <el-table-column prop="recipient" :label="t('sales.quotation.sentTo')" min-width="140" show-overflow-tooltip />
              <el-table-column :label="t('sales.quotation.sendResult')" width="100">
                <template #default="{ row }">{{ resultLabel(row.result) }}</template>
              </el-table-column>
              <el-table-column prop="senderName" :label="t('sales.quotation.sender')" width="90" />
            </el-table>
          </el-tab-pane>
        </el-tabs>

        <div v-if="detail.feedbackNote" class="qd-feedback">
          {{ t('sales.quotation.feedbackNote') }}：{{ detail.feedbackNote }}
        </div>

        <div class="qd-actions">
          <el-button
            v-if="detail.status === 'accepted' && !detail.contractId"
            v-permission="'sales:quote:to-contract'"
            type="primary"
            @click="doToContract"
          >
            {{ t('sales.quotation.toContract') }}
          </el-button>
          <el-button v-if="detail.contractId" @click="openContract">
            {{ t('sales.quotation.viewContract') }}
          </el-button>
        </div>
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
.quote-detail {
  min-height: 200px;
}

.qd-head {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  margin-bottom: var(--bs-space-3);
}

.qd-customer {
  color: var(--bs-color-fg-muted);
}

.qd-amount {
  margin-left: auto;
  font-weight: 600;
}

.qd-feedback {
  margin-top: var(--bs-space-2);
  color: var(--bs-color-fg-muted);
}

.qd-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--bs-space-3);
}
</style>
