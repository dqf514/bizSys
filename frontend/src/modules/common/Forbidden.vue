<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

defineOptions({ name: 'Forbidden' })

const { t } = useI18n()
const router = useRouter()
</script>

<template>
  <div class="forbidden">
    <div class="fb-code">403</div>
    <div class="fb-title">{{ t('common.error.forbiddenTitle') }}</div>
    <div class="fb-text">{{ t('common.error.forbiddenDesc') }}</div>
    <el-button type="primary" @click="router.push('/workbench')">{{ t('common.error.backToWorkbench') }}</el-button>
  </div>
</template>

<style scoped>
.forbidden {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--bs-space-3);
  background: var(--bs-color-bg-app);
}

.fb-code {
  font-size: 64px;
  font-weight: 700;
  color: var(--bs-color-primary);
}

.fb-title {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
}

.fb-text {
  color: var(--bs-color-fg-secondary);
}
</style>
