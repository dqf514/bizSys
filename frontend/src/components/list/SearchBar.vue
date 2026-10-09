<script setup lang="ts">
import { useI18n } from 'vue-i18n'

export interface SearchField {
  key: string
  labelKey: string
  type?: 'input' | 'select' | 'date' | 'daterange'
  placeholderKey?: string
  options?: { label: string; value: string | number }[]
  width?: number
  span?: number
}

const props = defineProps<{
  fields: SearchField[]
  modelValue: Record<string, unknown>
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: Record<string, unknown>): void
  (e: 'search'): void
  (e: 'reset'): void
}>()

const { t } = useI18n()

function getValue(key: string) {
  return props.modelValue[key]
}

function setValue(key: string, v: unknown) {
  emit('update:modelValue', { ...props.modelValue, [key]: v })
}

function placeholderOf(field: SearchField) {
  return field.placeholderKey
    ? t(field.placeholderKey)
    : t('common.form.placeholderInput')
}
</script>

<template>
  <div class="search-bar">
    <el-form inline label-position="top" class="search-form" @submit.prevent>
      <el-form-item
        v-for="field in fields"
        :key="field.key"
        :label="t(field.labelKey)"
        class="search-item"
      >
        <el-select
          v-if="field.type === 'select'"
          :model-value="getValue(field.key) as string"
          :placeholder="t('common.form.placeholderSelect')"
          clearable
          :style="{ width: (field.width ?? 180) + 'px' }"
          @update:model-value="setValue(field.key, $event)"
          @keyup.enter="emit('search')"
        >
          <el-option v-for="opt in field.options" :key="String(opt.value)" :label="opt.label" :value="opt.value" />
        </el-select>
        <el-date-picker
          v-else-if="field.type === 'daterange'"
          :model-value="getValue(field.key) as [string, string]"
          type="daterange"
          value-format="YYYY-MM-DD"
          :start-placeholder="t('common.form.startDate')"
          :end-placeholder="t('common.form.endDate')"
          :style="{ width: (field.width ?? 240) + 'px' }"
          @update:model-value="setValue(field.key, $event)"
        />
        <el-date-picker
          v-else-if="field.type === 'date'"
          :model-value="getValue(field.key) as string"
          type="date"
          value-format="YYYY-MM-DD"
          :placeholder="placeholderOf(field)"
          :style="{ width: (field.width ?? 180) + 'px' }"
          @update:model-value="setValue(field.key, $event)"
        />
        <el-input
          v-else
          :model-value="getValue(field.key) as string"
          :placeholder="placeholderOf(field)"
          clearable
          :style="{ width: (field.width ?? 180) + 'px' }"
          @update:model-value="setValue(field.key, $event)"
          @keyup.enter="emit('search')"
        />
      </el-form-item>

      <el-form-item class="search-btns">
        <el-button type="primary" @click="emit('search')">{{ t('common.action.search') }}</el-button>
        <el-button @click="emit('reset')">{{ t('common.action.reset') }}</el-button>
      </el-form-item>
    </el-form>
    <slot />
  </div>
</template>

<style scoped>
.search-form {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bs-space-2);
  align-items: flex-end;
}

.search-item {
  margin-right: 0;
  margin-bottom: 0;
}

.search-btns {
  margin-bottom: 0;
}
</style>
