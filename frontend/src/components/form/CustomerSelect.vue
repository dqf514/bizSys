<script setup lang="ts">
import { customerOptions } from '@/api/crm'
import RemoteSelect from './RemoteSelect.vue'
import type { CustomerOption } from '@/api/types'

const props = defineProps<{
  modelValue?: number | string | null
  placeholder?: string
  disabled?: boolean
  width?: string | number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: number | string | null): void
  (e: 'change', v: number | string | null, option?: CustomerOption): void
}>()

async function fetch(q: string) {
  try {
    const list = await customerOptions(q, 20)
    // keep the full payload (payOrg/taxNo/contactPerson/contactPhone) for auto-fill on change
    return (list ?? []).map((x) => ({ ...x }))
  } catch {
    return []
  }
}
</script>

<template>
  <RemoteSelect
    :model-value="props.modelValue ?? null"
    :fetch="fetch"
    :placeholder="props.placeholder"
    :disabled="props.disabled"
    :width="props.width ?? '100%'"
    @update:model-value="emit('update:modelValue', $event)"
    @change="(v, opt) => emit('change', v, opt as CustomerOption | undefined)"
  />
</template>
