<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ArrowDown, ArrowUp } from '@element-plus/icons-vue'
import type { DashboardWidgetPref } from '@/api/types'

defineOptions({ name: 'CustomizeDialog' })

const props = defineProps<{
  modelValue: boolean
  widgets: DashboardWidgetPref[]
  /** widget key -> i18n label key */
  labelKeys: Record<string, string>
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
  save: [DashboardWidgetPref[]]
}>()

const { t } = useI18n()

const draft = ref<DashboardWidgetPref[]>([])

watch(
  () => props.modelValue,
  (open) => {
    if (open) draft.value = props.widgets.map((w) => ({ ...w }))
  },
)

function move(index: number, delta: number) {
  const target = index + delta
  if (target < 0 || target >= draft.value.length) return
  const next = [...draft.value]
  const item = next[index]
  if (!item) return
  next.splice(index, 1)
  next.splice(target, 0, item)
  draft.value = next
}

function close() {
  emit('update:modelValue', false)
}

function confirm() {
  emit('save', draft.value.map((w) => ({ ...w })))
  close()
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="t('workbench.customizeTitle')"
    width="440px"
    @update:model-value="close"
  >
    <p class="tip">{{ t('workbench.customizeTip') }}</p>
    <ul class="widget-list">
      <li v-for="(w, i) in draft" :key="w.key" class="widget-row">
        <el-checkbox v-model="w.visible">{{ t(labelKeys[w.key] ?? w.key) }}</el-checkbox>
        <span class="row-actions">
          <el-button link size="small" :icon="ArrowUp" :disabled="i === 0" @click="move(i, -1)" />
          <el-button
            link
            size="small"
            :icon="ArrowDown"
            :disabled="i === draft.length - 1"
            @click="move(i, 1)"
          />
        </span>
      </li>
    </ul>
    <template #footer>
      <el-button @click="close">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" @click="confirm">{{ t('common.action.confirm') }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.tip {
  margin: 0 0 var(--bs-space-3);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.widget-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.widget-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--bs-space-1) 0;
}

.row-actions {
  display: inline-flex;
  gap: var(--bs-space-1);
}
</style>
