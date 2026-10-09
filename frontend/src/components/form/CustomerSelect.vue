<script setup lang="ts">
import { customerOptions } from '@/api/crm'
import RemoteSelect from './RemoteSelect.vue'
import type { RemoteOption } from './RemoteSelect.vue'

const props = defineProps<{
  modelValue?: number | string | null
  placeholder?: string
  disabled?: boolean
  width?: string | number
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: number | string | null): void
  (e: 'change', v: number | string | null, option?: RemoteOption): void
}>()

async function fetch(q: string) {
  try {
    const list = await customerOptions(q, 20)
    return (list ?? []).map((x) => ({ id: x.id, label: x.label, sub: x.sub }))
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
    @change="(v, opt) => emit('change', v, opt)"
  />
</template>
