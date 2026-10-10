<script setup lang="ts">
defineOptions({ name: 'WidgetShell' })

defineProps<{
  title: string
  /** red badge on the title (pending count); 0 hides it */
  badge?: number
  loading?: boolean
}>()
</script>

<template>
  <section class="widget-shell bs-hover-lift" v-loading="loading">
    <header class="widget-header">
      <span class="widget-title">
        {{ title }}
        <span v-if="badge" class="widget-badge">{{ badge > 99 ? '99+' : badge }}</span>
      </span>
      <span class="widget-actions">
        <slot name="actions" />
      </span>
    </header>
    <div class="widget-body">
      <slot />
    </div>
  </section>
</template>

<style scoped>
.widget-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  overflow: hidden;
}

.widget-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bs-space-2);
  padding: var(--bs-space-3) var(--bs-space-4);
  border-bottom: 1px solid var(--bs-color-border-subtle);
}

.widget-title {
  display: inline-flex;
  align-items: center;
  gap: var(--bs-space-2);
  font-size: var(--bs-typography-font-size-md);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.widget-badge {
  min-width: 18px;
  height: 18px;
  padding: 0 5px;
  border-radius: 9px;
  background: var(--bs-color-semantic-danger);
  color: var(--bs-color-fg-inverse);
  font-size: var(--bs-typography-font-size-xs);
  font-weight: 600;
  line-height: 18px;
  text-align: center;
}

.widget-actions {
  display: inline-flex;
  align-items: center;
  gap: var(--bs-space-1);
}

.widget-body {
  flex: 1;
  min-height: 0;
  padding: var(--bs-space-3) var(--bs-space-4);
  overflow: auto;
}
</style>
