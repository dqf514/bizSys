<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { portalHandovers } from '@/api/portal'
import type { PortalHandover } from '@/api/types'

defineOptions({ name: 'PortalHandovers' })

const { t } = useI18n()

const items = ref<PortalHandover[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const res = await portalHandovers()
    items.value = res.items || []
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div v-loading="loading" class="bs-page portal-handovers">
    <div class="bs-page-header">
      <h2 class="bs-page-title">{{ t('portal.portal.handovers.title') }}</h2>
    </div>

    <el-empty v-if="!loading && !items.length" :description="t('portal.portal.empty')" />

    <div class="portal-handover-list">
      <article v-for="h in items" :key="h.id" class="portal-handover-card">
        <div class="portal-handover-head">
          <span class="portal-handover-name">{{ h.sampleName || h.sampleNo }}</span>
          <span class="portal-handover-status">{{ h.statusText }}</span>
        </div>
        <div class="portal-handover-meta">
          <span>{{ t('portal.portal.handovers.field.no') }}：{{ h.handoverNo }}</span>
          <span>{{ t('portal.portal.handovers.field.sampleNo') }}：{{ h.sampleNo }}</span>
        </div>
        <div class="portal-handover-meta">
          <span>{{ t('portal.portal.handovers.field.qty') }}：{{ h.qty }}</span>
          <span>{{ t('portal.portal.handovers.field.time') }}：{{ h.handoverAt }}</span>
        </div>
        <div class="portal-handover-meta">
          <span>{{ t('portal.portal.handovers.field.users') }}：{{ h.handoverUserName }} → {{ h.receiveUserName }}</span>
        </div>
      </article>
    </div>
  </div>
</template>

<style scoped>
.portal-handovers {
  gap: var(--bs-space-4);
}

.portal-handover-list {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.portal-handover-card {
  padding: var(--bs-space-4);
  background: var(--bs-color-bg-surface);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.portal-handover-head {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: var(--bs-space-2);
}

.portal-handover-name {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.portal-handover-status {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.portal-handover-meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bs-space-3);
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-secondary);
}

@media (max-width: 767px) {
  .portal-handover-card {
    padding: var(--bs-space-3);
  }
}
</style>
