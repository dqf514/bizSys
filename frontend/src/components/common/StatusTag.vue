<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'

const props = defineProps<{
  status: string
  /** i18n prefix, e.g. `contract.contract.status` or `common.status` */
  i18nPrefix?: string
}>()

const { t } = useI18n()

const typeMap: Record<string, string> = {
  enabled: 'success',
  disabled: 'info',
  draft: 'info',
  approving: 'warning',
  approved: 'success',
  rejected: 'danger',
  voided: 'info',
  pending: 'warning',
  issued: 'success',
  invoicing: 'warning',
  invoiced: 'success',
  paid: 'success',
  settled: 'success',
  done: 'success',
  assigning: 'warning',
  assigned: '',
  in_progress: '',
  finished: 'success',
  closed: 'info',
  stopped: 'danger',
  in: 'success',
  out: 'warning',
  running: '',
  withdrawn: 'info',
  uploaded: '',
  sealed: 'success',
}

const type = computed(() => (typeMap[props.status] ?? 'info') as '' | 'success' | 'warning' | 'info' | 'danger')

const label = computed(() => {
  const prefix = props.i18nPrefix ?? 'common.status'
  const key = `${prefix}.${props.status}`
  const translated = t(key)
  if (translated !== key) return translated
  // 兼容 statusXxx 扁平键（contract/task/approval 等命名空间用的是这种写法）
  const camelKey = `${prefix}${props.status
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join('')}`
  const camel = t(camelKey)
  return camel === camelKey ? props.status : camel
})
</script>

<template>
  <el-tag :type="type" size="small" effect="light" round>{{ label }}</el-tag>
</template>
