<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

const { t } = useI18n()
const router = useRouter()
</script>

<template>
  <div class="not-found">
    <div class="nf-code">404</div>
    <div class="nf-text">{{ t('common.message.loadFailed') }}</div>
    <el-button type="primary" @click="router.push('/workbench')">{{ t('common.action.back') }}</el-button>
  </div>
</template>

<style scoped>
.not-found {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--bs-space-3);
  background: var(--bs-color-bg-app);
}

.nf-code {
  font-size: 64px;
  font-weight: 700;
  color: var(--bs-color-primary);
}

.nf-text {
  color: var(--bs-color-fg-secondary);
}
</style>
