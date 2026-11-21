<script setup lang="ts">
/** 全站统一页头：标题 + 右侧操作区。样式复用 page.css 的 .bs-page-header 体系。 */
defineOptions({ name: 'PageHeader' })

defineProps<{ title?: string }>()
</script>

<template>
  <div class="bs-page-header">
    <h1 class="bs-page-title">{{ title }}</h1>
    <div v-if="$slots.actions" class="bs-page-actions">
      <slot name="actions" />
    </div>
  </div>
</template>
