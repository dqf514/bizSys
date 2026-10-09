<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Download } from '@element-plus/icons-vue'

const props = defineProps<{
  exportFn: (params?: Record<string, unknown>) => Promise<void>
  params?: Record<string, unknown>
  disabled?: boolean
}>()

const { t } = useI18n()
const loading = ref(false)

async function run() {
  if (loading.value || props.disabled) return
  loading.value = true
  try {
    await props.exportFn(props.params)
  } catch {
    /* handled by http */
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <el-button :loading="loading" :disabled="props.disabled" @click="run">
    <el-icon><Download /></el-icon>
    <span>{{ t('common.action.export') }}</span>
  </el-button>
</template>
