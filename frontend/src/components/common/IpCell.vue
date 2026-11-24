<script setup lang="ts">
/**
 * IP 单元格：上行显示 IP，下行显示属地（省 / 市，字号更小、颜色更淡）。
 *
 * 属地由后端离线解析（ip2region），前端只做展示 —— 桌面表格与窄屏卡片共用同一组件。
 */
defineOptions({ name: 'IpCell' })

defineProps<{
  ip?: string
  region?: string
}>()
</script>

<template>
  <div class="ip-cell">
    <span class="ip-main">{{ ip || '-' }}</span>
    <span v-if="region" class="ip-region">{{ region }}</span>
  </div>
</template>

<style scoped>
.ip-cell {
  display: flex;
  flex-direction: column;
  line-height: 1.35;
  min-width: 0;
}

.ip-main {
  color: var(--bs-color-fg-default);
  word-break: break-all;
}

/* 属地：字号更小、颜色更淡（次要信息） */
.ip-region {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  word-break: break-all;
}
</style>
