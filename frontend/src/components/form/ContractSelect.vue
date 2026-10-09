<script setup lang="ts">
import { contractOptions } from '@/api/contract'
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
    // backend /contract/contracts/options returns approved contracts only
    const list = await contractOptions(q)
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
