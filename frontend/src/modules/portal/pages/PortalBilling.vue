<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { portalBilling } from '@/api/portal'
import type { PortalBilling } from '@/api/types'

defineOptions({ name: 'PortalBilling' })

const { t } = useI18n()

const data = ref<PortalBilling | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    data.value = await portalBilling()
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="bs-page portal-billing">
    <div class="bs-page-header">
      <h2 class="bs-page-title">{{ t('portal.portal.billing.title') }}</h2>
    </div>

    <div v-if="data" class="portal-summary-grid">
      <div class="portal-summary-card">
        <span class="portal-summary-value">{{ data.summary.totalAmount }}</span>
        <span class="portal-summary-label">{{ t('portal.portal.billing.statTotal') }}</span>
      </div>
      <div class="portal-summary-card">
        <span class="portal-summary-value">{{ data.summary.invoicedAmount }}</span>
        <span class="portal-summary-label">{{ t('portal.portal.home.statInvoiced') }}</span>
      </div>
      <div class="portal-summary-card">
        <span class="portal-summary-value">{{ data.summary.paidAmount }}</span>
        <span class="portal-summary-label">{{ t('portal.portal.home.statPaid') }}</span>
      </div>
      <div class="portal-summary-card">
        <span class="portal-summary-value">{{ data.summary.pendingAmount }}</span>
        <span class="portal-summary-label">{{ t('portal.portal.billing.statPending') }}</span>
      </div>
    </div>

    <el-empty v-if="!loading && !data?.items?.length" :description="t('portal.portal.empty')" />

    <section v-for="item in data?.items || []" :key="item.settlementId" class="bs-page-card">
      <div class="portal-billing-head">
        <div class="portal-billing-title">
          <span class="portal-billing-no">{{ item.settlementNo }}</span>
          <span class="portal-billing-status">{{ item.statusText }}</span>
        </div>
        <span class="portal-billing-amount">{{ item.amount }}</span>
      </div>

      <div v-if="item.invoices.length" class="portal-billing-block">
        <div class="portal-billing-block-title">{{ t('portal.portal.billing.invoiceTitle') }}</div>
        <div v-for="(inv, i) in item.invoices" :key="i" class="portal-billing-line">
          <span>{{ inv.invoiceNo }}</span>
          <span>{{ inv.statusText }}</span>
          <span>{{ inv.amount }}</span>
        </div>
      </div>

      <div v-if="item.payments.length" class="portal-billing-block">
        <div class="portal-billing-block-title">{{ t('portal.portal.billing.paymentTitle') }}</div>
        <div v-for="(pay, i) in item.payments" :key="i" class="portal-billing-line">
          <span>{{ pay.paymentNo }}</span>
          <span>{{ pay.statusText }}</span>
          <span>{{ pay.amount }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.portal-billing {
  gap: var(--bs-space-4);
}

.portal-summary-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--bs-space-3);
}

.portal-summary-card {
  background: var(--bs-color-bg-surface);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  padding: var(--bs-space-4);
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-1);
}

.portal-summary-value {
  font-size: var(--bs-typography-font-size-xl);
  font-weight: 700;
  color: var(--bs-color-primary);
}

.portal-summary-label {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.portal-billing-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: var(--bs-space-3);
}

.portal-billing-title {
  display: flex;
  flex-direction: column;
}

.portal-billing-no {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.portal-billing-status {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.portal-billing-amount {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 700;
  color: var(--bs-color-primary);
}

.portal-billing-block {
  margin-top: var(--bs-space-3);
}

.portal-billing-block-title {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  margin-bottom: var(--bs-space-1);
}

.portal-billing-line {
  display: grid;
  grid-template-columns: 1fr auto auto;
  gap: var(--bs-space-3);
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-secondary);
  padding: var(--bs-space-1) 0;
}
</style>
