<script setup lang="ts">
defineProps<{
  title?: string
  loading?: boolean
}>()
</script>

<template>
  <div class="list-page" v-loading="loading">
    <div class="list-page-header">
      <div class="list-page-title">{{ title }}</div>
      <div class="list-page-actions">
        <slot name="actions" />
      </div>
    </div>

    <div v-if="$slots.searchBar" class="list-page-search">
      <slot name="searchBar" />
    </div>

    <div v-if="$slots.statusTabs" class="list-page-tabs">
      <slot name="statusTabs" />
    </div>

    <div v-if="$slots.toolbar" class="list-page-toolbar">
      <slot name="toolbar" />
    </div>

    <div v-if="$slots.table" class="list-page-table">
      <slot name="table" />
    </div>

    <slot />
  </div>
</template>

<style scoped>
.list-page {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  height: 100%;
  min-height: 0;
  padding: var(--bs-space-3);
}

.list-page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.list-page-title {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.list-page-actions {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.list-page-search {
  flex-shrink: 0;
  padding: var(--bs-space-2) var(--bs-space-3);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
}

.list-page-tabs {
  flex-shrink: 0;
}

.list-page-toolbar {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  flex-shrink: 0;
}

.list-page-table {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
</style>
