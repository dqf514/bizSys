<script setup lang="ts">
import { useI18n } from 'vue-i18n'

export interface StatusTabItem {
  value: string
  labelKey?: string
  label?: string
  count?: number
}

const props = defineProps<{
  tabs: StatusTabItem[]
  modelValue: string
}>()

const emit = defineEmits<{ (e: 'update:modelValue', v: string): void }>()
const { t } = useI18n()

function labelOf(tab: StatusTabItem) {
  return tab.labelKey ? t(tab.labelKey) : (tab.label ?? tab.value)
}
</script>

<template>
  <div class="status-tabs">
    <button
      v-for="tab in props.tabs"
      :key="tab.value"
      type="button"
      class="status-tab"
      :class="{ active: tab.value === props.modelValue }"
      @click="emit('update:modelValue', tab.value)"
    >
      <span class="status-tab-label">{{ labelOf(tab) }}</span>
      <span v-if="tab.count !== undefined" class="status-tab-count">{{ tab.count }}</span>
    </button>
  </div>
</template>

<style scoped>
.status-tabs {
  display: flex;
  align-items: center;
  gap: var(--bs-space-1);
  border-bottom: 1px solid var(--bs-color-border-subtle);
}

.status-tab {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: none;
  border-bottom: 2px solid transparent;
  background: transparent;
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
  cursor: pointer;
}

.status-tab:hover {
  color: var(--bs-color-fg-default);
}

.status-tab.active {
  color: var(--bs-color-primary);
  border-bottom-color: var(--bs-color-primary);
  font-weight: 600;
}

.status-tab-count {
  min-width: 18px;
  padding: 0 5px;
  border-radius: var(--bs-radius-full);
  background: var(--bs-color-fill-light);
  font-size: 11px;
  color: var(--bs-color-fg-muted);
}

.status-tab.active .status-tab-count {
  background: var(--bs-color-brand-primary-soft);
  color: var(--bs-color-primary);
}
</style>
