<script setup lang="ts">
/**
 * 条件规则节点（递归）：一条规则要么是叶子（field + op + value），
 * 要么是**条件组**（rules 非空，按 logic and/or 组合，可嵌套）。
 *
 * 与后端 app/modules/oa/schemas.py::ConditionRule 的 AST 一一对应。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { Delete, Plus } from '@element-plus/icons-vue'
import type { OaConditionOp, OaConditionRule, OaField } from '@/api/types'

const props = withDefaults(
  defineProps<{
    rule: OaConditionRule
    /** 可引用的控件 */
    fields: OaField[]
    /** 嵌套深度（仅用于样式缩进） */
    depth?: number
  }>(),
  { depth: 0 },
)

const emit = defineEmits<{
  (e: 'update:rule', v: OaConditionRule): void
  (e: 'remove'): void
}>()

const { t } = useI18n()

defineOptions({ name: 'ConditionRuleNode' })

const OPS: OaConditionOp[] = [
  'eq',
  'ne',
  'gt',
  'gte',
  'lt',
  'lte',
  'in',
  'contains',
  'between',
  'empty',
  'not_empty',
]
const NO_VALUE_OPS: OaConditionOp[] = ['empty', 'not_empty']

const isGroup = computed(() => Boolean(props.rule.rules?.length))

function patch(next: Partial<OaConditionRule>) {
  emit('update:rule', { ...props.rule, ...next })
}

/** 区间值：[下限, 上限] */
const range = computed<[string, string]>(() => {
  const v = props.rule.value
  if (Array.isArray(v)) return [String(v[0] ?? ''), String(v[1] ?? '')]
  return ['', '']
})

function setRange(idx: 0 | 1, raw: string) {
  const next: [string, string] = [range.value[0], range.value[1]]
  next[idx] = raw
  patch({ value: next })
}

/** 集合值：逗号分隔的多个候选 */
const multiText = computed(() => {
  const v = props.rule.value
  if (Array.isArray(v)) return v.map((x) => String(x)).join(', ')
  return v === undefined || v === null ? '' : String(v)
})

function setMultiText(raw: string) {
  const list = raw
    .split(/[,，]/)
    .map((s) => s.trim())
    .filter((s) => s !== '')
  patch({ value: list })
}

function addChild() {
  patch({ rules: [...(props.rule.rules ?? []), { field: '', op: 'eq', value: '' }] })
}

function removeChild(idx: number) {
  const rules = [...(props.rule.rules ?? [])]
  rules.splice(idx, 1)
  patch({ rules })
}

function updateChild(idx: number, next: OaConditionRule) {
  const rules = [...(props.rule.rules ?? [])]
  rules[idx] = next
  patch({ rules })
}

/** 切换为条件组 / 退回叶子规则 */
function toGroup() {
  patch({ field: '', value: '', rules: [{ field: '', op: 'eq', value: '' }] })
}

function toLeaf() {
  patch({ rules: [] })
}
</script>

<template>
  <div class="cond-node" :class="{ 'cond-node--group': isGroup }">
    <!-- 条件组：可嵌套 -->
    <template v-if="isGroup">
      <div class="cond-group-head">
        <el-radio-group
          :model-value="rule.logic ?? 'and'"
          size="small"
          @update:model-value="patch({ logic: $event as 'and' | 'or' })"
        >
          <el-radio-button value="and">{{ t('oa.design.condAnd') }}</el-radio-button>
          <el-radio-button value="or">{{ t('oa.design.condOr') }}</el-radio-button>
        </el-radio-group>
        <el-button size="small" plain :icon="Plus" @click="addChild">
          {{ t('oa.design.condAdd') }}
        </el-button>
        <el-button size="small" plain @click="toLeaf">{{ t('oa.design.condToLeaf') }}</el-button>
        <el-button
          size="small"
          circle
          type="danger"
          plain
          :icon="Delete"
          :aria-label="t('common.action.delete')"
          @click="emit('remove')"
        />
      </div>
      <div class="cond-group-body">
        <ConditionRuleNode
          v-for="(child, ci) in rule.rules ?? []"
          :key="ci"
          :rule="child"
          :fields="fields"
          :depth="props.depth + 1"
          @update:rule="(v: OaConditionRule) => updateChild(ci, v)"
          @remove="removeChild(ci)"
        />
      </div>
    </template>

    <!-- 叶子规则 -->
    <template v-else>
      <div class="cond-rule">
        <el-select
          :model-value="rule.field ?? ''"
          :placeholder="t('oa.design.condField')"
          filterable
          @update:model-value="patch({ field: String($event ?? '') })"
        >
          <el-option v-for="f in fields" :key="f.key" :value="f.key" :label="f.label || f.key" />
        </el-select>
        <el-select
          :model-value="rule.op"
          class="cond-op"
          @update:model-value="patch({ op: $event as OaConditionOp })"
        >
          <el-option v-for="op in OPS" :key="op" :value="op" :label="t(`oa.design.condOp.${op}`)" />
        </el-select>

        <!-- 区间：双值输入 -->
        <template v-if="rule.op === 'between'">
          <el-input
            :model-value="range[0]"
            :placeholder="t('oa.design.condRange')"
            @update:model-value="setRange(0, String($event ?? ''))"
          />
          <el-input
            :model-value="range[1]"
            :placeholder="t('oa.design.condRangeTo')"
            @update:model-value="setRange(1, String($event ?? ''))"
          />
        </template>

        <!-- 集合：逗号分隔 -->
        <el-input
          v-else-if="rule.op === 'in'"
          :model-value="multiText"
          :placeholder="t('oa.design.condMultiValues')"
          @update:model-value="setMultiText(String($event ?? ''))"
        />

        <el-input
          v-else-if="!NO_VALUE_OPS.includes(rule.op)"
          :model-value="rule.value === undefined || rule.value === null ? '' : String(rule.value)"
          :placeholder="t('oa.design.condValue')"
          @update:model-value="patch({ value: String($event ?? '') })"
        />

        <el-button
          size="small"
          circle
          type="danger"
          plain
          :icon="Delete"
          :aria-label="t('common.action.delete')"
          @click="emit('remove')"
        />
        <el-button size="small" plain @click="toGroup">{{ t('oa.design.condToGroup') }}</el-button>
      </div>
    </template>
  </div>
</template>

<style scoped>
.cond-node {
  width: 100%;
}

.cond-node--group {
  padding: var(--bs-space-2);
  border: 1px dashed var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-sm);
  background: var(--bs-color-fill-lighter);
}

.cond-group-head {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  margin-bottom: var(--bs-space-2);
  flex-wrap: wrap;
}

.cond-group-body {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  padding-left: var(--bs-space-2);
  border-left: 2px solid var(--bs-color-border-subtle);
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
  flex: 0 0 92px;
}
</style>
