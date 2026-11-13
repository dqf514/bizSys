<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import StatusTag from '@/components/common/StatusTag.vue'
import { getQuotation, sendQuotation } from '@/api/sales'
import type { Quotation } from '@/api/types'
import QuotationPreview from '../components/QuotationPreview.vue'

defineOptions({ name: 'QuotationPrint' })

const { t } = useI18n()
const route = useRoute()

const loading = ref(false)
const detail = ref<Quotation | null>(null)
const marking = ref(false)

async function load() {
  const id = Number(route.params.id)
  if (!id) return
  loading.value = true
  try {
    detail.value = await getQuotation(id)
    document.title = `${detail.value.quoteNo || detail.value.id} ${detail.value.title}`
  } catch {
    detail.value = null
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

function doPrint() {
  window.print()
}

async function markSent() {
  if (!detail.value) return
  marking.value = true
  try {
    detail.value = await sendQuotation(detail.value.id, 'print')
    ElMessage.success(t('common.message.saveSuccess'))
  } catch {
    /* http notifies */
  } finally {
    marking.value = false
  }
}

function goBack() {
  if (window.history.length > 1) window.history.back()
  else window.close()
}
</script>

<template>
  <div class="print-page" v-loading="loading">
    <div class="pp-toolbar">
      <el-button @click="goBack">{{ t('sales.print.back') }}</el-button>
      <StatusTag v-if="detail" :status="detail.status" i18n-prefix="sales.quotation.status" />
      <el-button
        v-if="detail && ['approved', 'sent'].includes(detail.status)"
        v-permission="'sales:quote:send'"
        :loading="marking"
        @click="markSent"
      >
        {{ t('sales.print.markSent') }}
      </el-button>
      <el-button type="primary" @click="doPrint">{{ t('sales.print.print') }}</el-button>
    </div>

    <div v-if="detail" class="pp-sheet">
      <div v-if="!['approved', 'sent', 'accepted'].includes(detail.status)" class="pp-watermark">
        {{ t('sales.print.draftWatermark') }}
      </div>
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
    </div>
  </div>
</template>

<style scoped>
.print-page {
  min-height: 100vh;
  background: var(--bs-color-bg-muted, #f5f7fa);
  padding: var(--bs-space-3);
}

.pp-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: var(--bs-space-2);
  max-width: 900px;
  margin: 0 auto var(--bs-space-3);
}

.pp-sheet {
  position: relative;
  max-width: 900px;
  margin: 0 auto;
}

.pp-watermark {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 48px;
  font-weight: 700;
  color: var(--bs-color-danger, #f56c6c);
  opacity: 0.12;
  pointer-events: none;
  transform: rotate(-18deg);
  z-index: 1;
}

@media print {
  .print-page {
    background: #fff;
    padding: 0;
  }

  .pp-toolbar {
    display: none;
  }

  .pp-sheet {
    max-width: none;
  }

  @page {
    size: A4;
    margin: 16mm 14mm;
  }
}
</style>
