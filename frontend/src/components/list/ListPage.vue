<script setup lang="ts">
import PageHeader from '@/components/common/PageHeader.vue'

defineProps<{
  title?: string
  loading?: boolean
}>()
</script>

<template>
  <div class="bs-page bs-page--fill list-page" v-loading="loading">
    <PageHeader :title="title">
      <template #actions>
        <slot name="actions" />
      </template>
    </PageHeader>

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
  /* 承重链：el-table 拿的是 height="100%"，父链一旦没有确定高度表格就会塌成 0 高 */
  height: 100%;
  min-height: 0;
  /* 外层页面已提供内容边距时，父级设 --list-page-padding: 0，避免双重内边距 */
  padding: var(--list-page-padding, var(--bs-layout-content-padding));
}

/* 检索区：白卡 */
.list-page-search {
  flex-shrink: 0;
  padding: var(--bs-space-2) var(--bs-layout-content-padding);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
}

/* 页签区：与检索区同规格的白卡，使页签文字与检索字段左边线对齐 */
.list-page-tabs {
  flex-shrink: 0;
  padding: 0;
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
}

/* 卡片自带边框，去掉页签条自身的下边框，避免双线 */
.list-page-tabs :deep(.status-tabs) {
  border-bottom: none;
}

/* 首个页签补左内边距，使页签文字与检索字段左边线对齐 */
.list-page-tabs :deep(.status-tab:first-child) {
  padding-left: var(--bs-layout-content-padding);
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
