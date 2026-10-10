<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { getSmartHistory } from '@/composables/smartInputHistory'

const props = withDefaults(
  defineProps<{
    modelValue?: string
    /** history bucket key, e.g. "contract.sealType" */
    field: string
    placeholder?: string
    maxlength?: number
    disabled?: boolean
    clearable?: boolean
  }>(),
  {
    modelValue: '',
    disabled: false,
    clearable: true,
  },
)

const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
}>()

const { t } = useI18n()

function querySearch(q: string, cb: (items: { value: string }[]) => void) {
  const needle = q.trim().toLowerCase()
  const history = getSmartHistory(props.field)
  const matched = needle ? history.filter((x) => x.toLowerCase().includes(needle)) : history
  cb(matched.map((value) => ({ value })))
}

function onUpdate(v: string) {
  emit('update:modelValue', v)
}
</script>

<template>
  <el-autocomplete
    :model-value="props.modelValue"
    :fetch-suggestions="querySearch"
    :placeholder="props.placeholder || t('common.form.placeholderInput')"
    :maxlength="props.maxlength"
    :disabled="props.disabled"
    :clearable="props.clearable"
    :trigger-on-focus="true"
    style="width: 100%"
    @update:model-value="onUpdate"
  />
</template>
