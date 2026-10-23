<script setup lang="ts">
/** 条件组编辑器：{logic: and/or, rules: [{field, op, value}]}，用于 showWhen/requiredWhen/readonlyWhen。 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Delete, Plus } from '@element-plus/icons-vue'
import type { OaConditionGroup, OaConditionOp, OaField } from '@/api/types'

const props = defineProps<{
  modelValue: OaConditionGroup | null | undefined
  /** 可引用的控件（不含自身与布局控件） */
  fields: OaField[]
  title: string
}>()
const emit = defineEmits<{ (e: 'update:modelValue', v: OaConditionGroup | null): void }>()

const { t } = useI18n()

const OPS: OaConditionOp[] = ['eq', 'ne', 'gt', 'gte', 'lt', 'lte', 'contains', 'empty', 'not_empty']
const NO_VALUE_OPS: OaConditionOp[] = ['empty', 'not_empty']

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

function patchRule(idx: number, patch: Partial<OaConditionGroup['rules'][number]>) {
  if (!group.value) return
  const rules = group.value.rules.map((r, i) => (i === idx ? { ...r, ...patch } : r))
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
      <div v-for="(r, ri) in group.rules" :key="ri" class="cond-rule">
        <el-select
          :model-value="r.field"
          :placeholder="t('oa.design.condField')"
          filterable
          @update:model-value="patchRule(ri, { field: String($event ?? '') })"
        >
          <el-option v-for="f in fields" :key="f.key" :value="f.key" :label="f.label || f.key" />
        </el-select>
        <el-select
          :model-value="r.op"
          class="cond-op"
          @update:model-value="patchRule(ri, { op: $event as OaConditionOp })"
        >
          <el-option v-for="op in OPS" :key="op" :value="op" :label="t(`oa.design.condOp.${op}`)" />
        </el-select>
        <el-input
          v-if="!NO_VALUE_OPS.includes(r.op)"
          :model-value="r.value"
          :placeholder="t('oa.design.condValue')"
          @update:model-value="patchRule(ri, { value: String($event ?? '') })"
        />
        <el-button size="small" circle type="danger" plain :icon="Delete" @click="removeRule(ri)" />
      </div>
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

.cond-rule {
  display: flex;
  align-items: center;
  gap: 4px;
}

.cond-rule .el-select,
.cond-rule .el-input {
  flex: 1;
  min-width: 0;
}

.cond-rule .cond-op {
  flex: 0 0 76px;
}
</style>
