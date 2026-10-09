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
}

const type = computed(() => (typeMap[props.status] ?? 'info') as '' | 'success' | 'warning' | 'info' | 'danger')

const label = computed(() => {
  const prefix = props.i18nPrefix ?? 'common.status'
  const key = `${prefix}.${props.status}`
  const translated = t(key)
  return translated === key ? props.status : translated
})
</script>

<template>
  <el-tag :type="type" size="small" effect="light" round>{{ label }}</el-tag>
</template>
