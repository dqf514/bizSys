<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { portalProgress } from '@/api/portal'
import type { PortalProgress, PortalProgressStage } from '@/api/types'

defineOptions({ name: 'PortalProgress' })

const { t } = useI18n()

const data = ref<PortalProgress | null>(null)
const loading = ref(false)

const stages = computed(() => data.value?.stages || [])

/** 按环节分组，便于手机上一屏一环节地看 */
const grouped = computed(() => {
  const order = ['entrust', 'task', 'settlement', 'invoice', 'payment']
  const map = new Map<string, PortalProgressStage[]>()
  for (const s of stages.value) {
    const arr = map.get(s.stage) || []
    arr.push(s)
    map.set(s.stage, arr)
  }
  return order
    .filter((k) => map.has(k))
    .map((k) => {
      const items = map.get(k) ?? []
      return { stage: k, text: items[0]?.stageText ?? '', items }
    })
})

async function load() {
  loading.value = true
  try {
    data.value = await portalProgress()
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="bs-page portal-progress">
    <div class="bs-page-header">
      <h2 class="bs-page-title">{{ t('portal.portal.progress.title') }}</h2>
    </div>

    <div v-if="data" class="portal-summary-grid">
      <div class="portal-summary-card">
        <span class="portal-summary-value">{{ data.summary.entrustCount }}</span>
        <span class="portal-summary-label">{{ t('portal.portal.home.statEntrust') }}</span>
      </div>
      <div class="portal-summary-card">
        <span class="portal-summary-value">{{ data.summary.taskCount }}</span>
        <span class="portal-summary-label">{{ t('portal.portal.home.statTask') }}</span>
      </div>
      <div class="portal-summary-card">
        <span class="portal-summary-value">{{ data.summary.settledAmount }}</span>
        <span class="portal-summary-label">{{ t('portal.portal.home.statSettled') }}</span>
      </div>
      <div class="portal-summary-card">
        <span class="portal-summary-value">{{ data.summary.invoicedAmount }}</span>
        <span class="portal-summary-label">{{ t('portal.portal.home.statInvoiced') }}</span>
      </div>
      <div class="portal-summary-card">
        <span class="portal-summary-value">{{ data.summary.paidAmount }}</span>
        <span class="portal-summary-label">{{ t('portal.portal.home.statPaid') }}</span>
      </div>
    </div>

    <el-empty v-if="!loading && !stages.length" :description="t('portal.portal.empty')" />

    <section v-for="g in grouped" :key="g.stage" class="bs-page-card">
      <div class="portal-section-title">{{ g.text }}</div>
      <div class="portal-stage-list">
        <div v-for="(item, idx) in g.items" :key="idx" class="portal-stage-item">
          <div class="portal-stage-main">
            <span class="portal-stage-title">{{ item.title || item.refNo }}</span>
            <span class="portal-stage-ref">{{ item.refNo }}</span>
          </div>
          <div class="portal-stage-side">
            <span class="portal-stage-status">{{ item.statusText }}</span>
            <span v-if="item.amount != null" class="portal-stage-amount">{{ item.amount }}</span>
            <el-progress
              v-if="item.progress != null"
              :percentage="item.progress"
              :stroke-width="6"
              class="portal-stage-progress"
            />
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.portal-progress {
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

.portal-section-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
  margin-bottom: var(--bs-space-3);
}

.portal-stage-list {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.portal-stage-item {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bs-space-2);
  justify-content: space-between;
  align-items: center;
}

.portal-stage-main {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.portal-stage-title {
  color: var(--bs-color-fg-default);
  font-weight: 500;
}

.portal-stage-ref {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.portal-stage-side {
  display: flex;
  align-items: center;
  gap: var(--bs-space-3);
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-secondary);
}

.portal-stage-amount {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.portal-stage-progress {
  width: 100%;
}
</style>
