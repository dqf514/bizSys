<script setup lang="ts">
/**
 * 条件组编辑器：{logic: and/or, rules: [{field, op, value}]}，用于 showWhen/requiredWhen/readonlyWhen。
 * 规则可嵌套条件组（ConditionRuleNode 递归渲染），与后端 ConditionRule AST 对齐。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Plus } from '@element-plus/icons-vue'
import type { OaConditionGroup, OaConditionRule, OaField } from '@/api/types'

const props = defineProps<{
  modelValue: OaConditionGroup | null | undefined
  /** 可引用的控件（不含自身与布局控件） */
  fields: OaField[]
  title: string
}>()
const emit = defineEmits<{ (e: 'update:modelValue', v: OaConditionGroup | null): void }>()

const { t } = useI18n()

const enabled = computed({
  get: () => Boolean(props.modelValue?.rules?.length),
  set: (on: boolean) => {
    if (on) emit('update:modelValue', { logic: 'and', rules: [{ field: '', op: 'eq', value: '' }] })
    else emit('update:modelValue', null)
  },
})

const group = computed(() => props.modelValue ?? null)

function update(patch: Partial<OaConditionGroup>) {
  if (group.value) emit('update:modelValue', { ...group.value, ...patch })
}

function addRule() {
  if (!group.value) return
  update({ rules: [...group.value.rules, { field: '', op: 'eq', value: '' }] })
}

function removeRule(idx: number) {
  if (!group.value) return
  const rules = group.value.rules.filter((_, i) => i !== idx)
  emit('update:modelValue', rules.length ? { ...group.value, rules } : null)
}

function patchRule(idx: number, next: OaConditionRule) {
  if (!group.value) return
  const rules = group.value.rules.map((r, i) => (i === idx ? next : r))
  update({ rules })
}
</script>

<template>
  <div class="cond-editor">
    <div class="cond-head">
      <span class="cond-title">{{ title }}</span>
      <el-switch :model-value="enabled" @update:model-value="enabled = Boolean($event)" />
    </div>
    <template v-if="group">
      <el-radio-group
        :model-value="group.logic"
        size="small"
        @update:model-value="update({ logic: $event as 'and' | 'or' })"
      >
        <el-radio-button value="and">{{ t('oa.design.condAnd') }}</el-radio-button>
        <el-radio-button value="or">{{ t('oa.design.condOr') }}</el-radio-button>
      </el-radio-group>
      <ConditionRuleNode
        v-for="(r, ri) in group.rules"
        :key="ri"
        :rule="r"
        :fields="fields"
        @update:rule="(v: OaConditionRule) => patchRule(ri, v)"
        @remove="removeRule(ri)"
      />
      <el-button size="small" plain :icon="Plus" @click="addRule">{{ t('oa.design.condAdd') }}</el-button>
    </template>
  </div>
</template>

<style scoped>
.cond-editor {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  padding: var(--bs-space-2);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
}

.cond-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.cond-title {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}
</style>
