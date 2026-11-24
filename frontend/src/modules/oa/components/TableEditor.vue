<script setup lang="ts">
/** OA 明细表编辑器（E1 企业微信 Table 控件）。
 * mode="columns"：设计态 —— 编辑子列（标识 / 标题 / 类型 / 选项）。
 * mode="rows"   ：运行态 —— 增删明细行并编辑单元格（提交为对象数组）。
 */
import { useI18n } from 'vue-i18n'
import { Delete, Plus } from '@element-plus/icons-vue'
import type { OaColumn } from '@/api/types'

const props = defineProps<{
  mode: 'columns' | 'rows'
  /** 设计态：子列定义；运行态：子列定义（决定单元格渲染） */
  columns?: OaColumn[]
  /** 运行态：明细行 */
  modelValue?: Record<string, unknown>[]
  disabled?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:columns', v: OaColumn[]): void
  (e: 'update:modelValue', v: Record<string, unknown>[]): void
}>()

const { t } = useI18n()

const COLUMN_TYPES: OaColumn['type'][] = ['text', 'textarea', 'number', 'money', 'date', 'select']

/* ---------- 设计态：子列 ---------- */
function addColumn() {
  const cols = props.columns ?? []
  emit('update:columns', [
    ...cols,
    {
      key: `col${cols.length + 1}`,
      label: t('oa.design.columnLabel', { n: cols.length + 1 }),
      type: 'text',
      required: false,
    },
  ])
}

function removeColumn(idx: number) {
  emit('update:columns', (props.columns ?? []).filter((_, i) => i !== idx))
}

function patchColumn(idx: number, patch: Partial<OaColumn>) {
  emit(
    'update:columns',
    (props.columns ?? []).map((c, i) => (i === idx ? { ...c, ...patch } : c)),
  )
}

/** 下拉列的选项文本（一行一个，逗号分隔编辑） */
function optionsText(c: OaColumn): string {
  return (c.options ?? []).join(', ')
}

function setOptions(c: OaColumn, text: string) {
  patchColumnByKey(c.key, {
    options: text
      .split(/[,，]/)
      .map((s) => s.trim())
      .filter(Boolean),
  })
}

function patchColumnByKey(key: string, patch: Partial<OaColumn>) {
  emit(
    'update:columns',
    (props.columns ?? []).map((c) => (c.key === key ? { ...c, ...patch } : c)),
  )
}

/* ---------- 运行态：明细行 ---------- */
function rows(): Record<string, unknown>[] {
  return Array.isArray(props.modelValue) ? props.modelValue : []
}

function addRow() {
  const row: Record<string, unknown> = {}
  for (const c of props.columns ?? []) row[c.key] = ''
  emit('update:modelValue', [...rows(), row])
}

function removeRow(idx: number) {
  emit('update:modelValue', rows().filter((_, i) => i !== idx))
}

function cellValue(row: Record<string, unknown>, key: string): unknown {
  return row?.[key]
}

function setCell(idx: number, key: string, v: unknown) {
  const next = rows().map((r, i) => (i === idx ? { ...r, [key]: v } : r))
  emit('update:modelValue', next)
}
</script>

<template>
  <!-- 设计态：子列定义 -->
  <div v-if="props.mode === 'columns'" class="te-columns">
    <div v-for="(c, ci) in props.columns ?? []" :key="ci" class="te-col-row">
      <el-input
        :model-value="c.key"
        :placeholder="t('oa.design.columnKey')"
        style="width: 110px"
        @update:model-value="patchColumn(ci, { key: String($event ?? '') })"
      />
      <el-input
        :model-value="c.label"
        :placeholder="t('oa.design.columnLabel', { n: ci + 1 })"
        style="flex: 1; min-width: 80px"
        @update:model-value="patchColumn(ci, { label: String($event ?? '') })"
      />
      <el-select
        :model-value="c.type"
        style="width: 100px"
        @update:model-value="patchColumn(ci, { type: $event as OaColumn['type'] })"
      >
        <el-option
          v-for="ct in COLUMN_TYPES"
          :key="ct"
          :value="ct"
          :label="t(`oa.columnType.${ct}`)"
        />
      </el-select>
      <el-checkbox
        :model-value="Boolean(c.required)"
        @update:model-value="patchColumn(ci, { required: Boolean($event) })"
      >
        {{ t('oa.design.columnRequired') }}
      </el-checkbox>
      <el-input
        v-if="c.type === 'select'"
        :model-value="optionsText(c)"
        :placeholder="t('oa.design.columnOptions')"
        style="flex: 1; min-width: 90px"
        @update:model-value="setOptions(c, String($event ?? ''))"
      />
      <el-button
        size="small"
        circle
        :icon="Delete"
        type="danger"
        plain
        :aria-label="t('common.action.delete')"
        @click="removeColumn(ci)"
      />
    </div>
    <el-button size="small" plain type="primary" :icon="Plus" @click="addColumn">
      {{ t('oa.design.columnAdd') }}
    </el-button>
  </div>

  <!-- 运行态：明细行 -->
  <div v-else class="te-rows">
    <div v-if="!(props.columns ?? []).length" class="te-empty">{{ t('oa.form.tableNoColumns') }}</div>
    <div v-for="(row, ri) in rows()" :key="ri" class="te-row">
      <div class="te-row-cells">
        <template v-for="c in props.columns ?? []" :key="c.key">
          <el-input
            v-if="c.type === 'text'"
            :model-value="String(cellValue(row, c.key) ?? '')"
            :disabled="props.disabled"
            @update:model-value="setCell(ri, c.key, String($event ?? ''))"
          />
          <el-input
            v-else-if="c.type === 'textarea'"
            type="textarea"
            :rows="2"
            :model-value="String(cellValue(row, c.key) ?? '')"
            :disabled="props.disabled"
            @update:model-value="setCell(ri, c.key, String($event ?? ''))"
          />
          <el-input-number
            v-else-if="c.type === 'number'"
            :model-value="(cellValue(row, c.key) as number) ?? undefined"
            :controls-position="false"
            :disabled="props.disabled"
            style="width: 100%"
            @update:model-value="setCell(ri, c.key, $event ?? '')"
          />
          <el-input-number
            v-else-if="c.type === 'money'"
            :model-value="(cellValue(row, c.key) as number) ?? undefined"
            :precision="2"
            :controls-position="false"
            :disabled="props.disabled"
            style="width: 100%"
            @update:model-value="setCell(ri, c.key, $event ?? '')"
          />
          <el-date-picker
            v-else-if="c.type === 'date'"
            :model-value="String(cellValue(row, c.key) ?? '')"
            type="date"
            value-format="YYYY-MM-DD"
            :disabled="props.disabled"
            style="width: 100%"
            @update:model-value="setCell(ri, c.key, String($event ?? ''))"
          />
          <el-select
            v-else-if="c.type === 'select'"
            :model-value="String(cellValue(row, c.key) ?? '')"
            :disabled="props.disabled"
            clearable
            style="width: 100%"
            @update:model-value="setCell(ri, c.key, String($event ?? ''))"
          >
            <el-option v-for="o in c.options ?? []" :key="o" :value="o" :label="o" />
          </el-select>
        </template>
      </div>
      <el-button
        v-if="!props.disabled"
        size="small"
        circle
        :icon="Delete"
        type="danger"
        plain
        :aria-label="t('common.action.delete')"
        @click="removeRow(ri)"
      />
    </div>
    <el-button v-if="!props.disabled" size="small" plain type="primary" :icon="Plus" @click="addRow">
      {{ t('oa.form.tableAddRow') }}
    </el-button>
  </div>
</template>

<style scoped>
.te-columns,
.te-rows {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  align-items: flex-start;
}

.te-col-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 4px;
}

.te-row {
  width: 100%;
  display: flex;
  align-items: flex-start;
  gap: var(--bs-space-2);
}

.te-row-cells {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  gap: var(--bs-space-2);
}

.te-row-cells > * {
  flex: 1;
  min-width: 120px;
}

.te-empty {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}
</style>
