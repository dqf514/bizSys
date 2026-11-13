<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { QuotationItem, QuoteTemplateLayout } from '@/api/types'

defineOptions({ name: 'QuotationPreview' })

const props = defineProps<{
  layout?: Partial<QuoteTemplateLayout> | null
  quoteNo?: string
  title?: string
  customerName?: string
  contactName?: string
  contactPhone?: string
  validUntil?: string
  items?: QuotationItem[]
  totalAmount?: number
  taxRate?: number
  currency?: string
  status?: string
}>()

const { t } = useI18n()

const layout = computed(() => props.layout ?? {})

function colVisible(key: string): boolean {
  const conf = (layout.value.itemColumns ?? []).find((c) => c.key === key)
  return conf ? conf.visible !== false : true
}

function colLabel(key: string, labelKey: string): string {
  const conf = (layout.value.itemColumns ?? []).find((c) => c.key === key)
  return conf?.label?.trim() || t(labelKey)
}

const safeItems = computed(() => props.items ?? [])

const subtotal = computed(() =>
  safeItems.value.reduce((s, it) => s + Number(it.qty || 0) * Number(it.unitPrice || 0), 0),
)

const totalWithTax = computed(() => subtotal.value * (1 + Number(props.taxRate ?? 0) / 100))

function fmt(n: number): string {
  return Number.isFinite(n) ? n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '-'
}
</script>

<template>
  <div class="quote-preview">
    <!-- 抬头（模板 HTML） -->
    <div v-if="layout.headerHtml" class="qp-header" v-html="layout.headerHtml" />
    <div class="qp-meta">
      <div class="qp-meta-row"><span class="qp-label">{{ t('sales.print.quoteNo') }}</span>{{ quoteNo || '-' }}</div>
      <div class="qp-meta-row"><span class="qp-label">{{ t('sales.print.billTo') }}</span>{{ customerName || '-' }}</div>
      <div class="qp-meta-row">
        <span class="qp-label">{{ t('sales.print.contact') }}</span>
        {{ [contactName, contactPhone].filter(Boolean).join(' ') || '-' }}
      </div>
      <div class="qp-meta-row">
        <span class="qp-label">{{ t('sales.print.validUntil') }}</span>{{ validUntil || '-' }}
      </div>
    </div>
    <div v-if="layout.introHtml" class="qp-intro" v-html="layout.introHtml" />

    <table class="qp-table">
      <thead>
        <tr>
          <th class="qp-seq">{{ t('sales.print.seq') }}</th>
          <th>{{ t('sales.print.name') }}</th>
          <th v-if="colVisible('spec')">{{ colLabel('spec', 'sales.print.spec') }}</th>
          <th class="qp-num">{{ t('sales.print.qty') }}</th>
          <th v-if="colVisible('unit')">{{ colLabel('unit', 'sales.print.unit') }}</th>
          <th class="qp-num">{{ t('sales.print.unitPrice') }}</th>
          <th class="qp-num">{{ t('sales.print.amount') }}</th>
          <th v-if="colVisible('remark')">{{ colLabel('remark', 'sales.print.remark') }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="(it, idx) in safeItems" :key="idx">
          <td class="qp-seq">{{ idx + 1 }}</td>
          <td>{{ it.name }}</td>
          <td v-if="colVisible('spec')">{{ it.spec }}</td>
          <td class="qp-num">{{ it.qty }}</td>
          <td v-if="colVisible('unit')">{{ it.unit }}</td>
          <td class="qp-num">{{ fmt(Number(it.unitPrice || 0)) }}</td>
          <td class="qp-num">{{ fmt(Number(it.qty || 0) * Number(it.unitPrice || 0)) }}</td>
          <td v-if="colVisible('remark')">{{ it.remark }}</td>
        </tr>
        <tr v-if="!safeItems.length">
          <td class="qp-empty" :colspan="8">-</td>
        </tr>
      </tbody>
      <tfoot>
        <tr>
          <td class="qp-num qp-total-label" :colspan="4">{{ t('sales.print.subtotal') }}</td>
          <td class="qp-num" :colspan="4">{{ currency || 'CNY' }} {{ fmt(subtotal) }}</td>
        </tr>
        <tr>
          <td class="qp-num qp-total-label" :colspan="4">
            {{ t('sales.print.totalWithTax') }}（{{ t('sales.print.taxRate') }} {{ taxRate ?? 0 }}%）
          </td>
          <td class="qp-num qp-grand" :colspan="4">{{ currency || 'CNY' }} {{ fmt(totalWithTax) }}</td>
        </tr>
      </tfoot>
    </table>

    <div v-if="layout.termsHtml" class="qp-terms">
      <div class="qp-terms-title">{{ t('sales.print.terms') }}</div>
      <div v-html="layout.termsHtml" />
    </div>
    <div v-if="layout.footerHtml" class="qp-footer" v-html="layout.footerHtml" />
    <div class="qp-sign">
      <span>{{ t('sales.print.signature') }}</span>
      <span>{{ t('sales.print.customerSign') }}</span>
    </div>
  </div>
</template>

<style scoped>
.quote-preview {
  background: var(--bs-color-bg-paper, #fff);
  color: var(--bs-color-fg-default);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  padding: var(--bs-space-4);
  font-size: var(--bs-typography-font-size-sm);
}

.qp-header :deep(h2) {
  margin: 0 0 var(--bs-space-1);
  text-align: center;
}

.qp-header :deep(p) {
  margin: 0 0 var(--bs-space-2);
  text-align: center;
  color: var(--bs-color-fg-muted);
}

.qp-meta {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--bs-space-1) var(--bs-space-4);
  margin: var(--bs-space-2) 0;
}

.qp-label {
  color: var(--bs-color-fg-muted);
  margin-right: var(--bs-space-2);
}

.qp-intro {
  margin: var(--bs-space-2) 0;
}

.qp-table {
  width: 100%;
  border-collapse: collapse;
  margin: var(--bs-space-2) 0;
}

.qp-table th,
.qp-table td {
  border: 1px solid var(--bs-color-border-subtle);
  padding: var(--bs-space-1) var(--bs-space-2);
  text-align: left;
}

.qp-table th {
  background: var(--bs-color-bg-muted, #f5f7fa);
}

.qp-num {
  text-align: right !important;
  white-space: nowrap;
}

.qp-seq {
  text-align: center !important;
  width: 40px;
}

.qp-empty {
  text-align: center !important;
  color: var(--bs-color-fg-muted);
}

.qp-total-label {
  font-weight: 600;
}

.qp-grand {
  font-weight: 700;
}

.qp-terms {
  margin-top: var(--bs-space-3);
}

.qp-terms-title {
  font-weight: 600;
  margin-bottom: var(--bs-space-1);
}

.qp-terms :deep(p) {
  margin: var(--bs-space-1) 0;
}

.qp-footer {
  margin-top: var(--bs-space-3);
  color: var(--bs-color-fg-muted);
}

.qp-sign {
  display: flex;
  justify-content: space-between;
  margin-top: var(--bs-space-4);
}
</style>
