<script setup lang="ts">
/** OA 表单设计器（复刻 TPCworkflow FormDesigner 三栏交互，数据模型保持 bizSys fields[]）。
 * 左：字段类型面板（点击或拖拽添加）；中：画布（FormRenderer 设计模式实时预览，
 * 点击选中 / 拖拽排序 / 复制 / 删除）；右：字段属性（key/label/类型/必填/选项/占位/maxlength/exposeVariable）。
 */
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Bottom, Delete, Top } from '@element-plus/icons-vue'
import FormRenderer from './FormRenderer.vue'
import type { OaField, OaFieldType } from '@/api/types'

const props = defineProps<{ fields: OaField[] }>()
const emit = defineEmits<{ (e: 'update:fields', v: OaField[]): void }>()

const { t } = useI18n()

const OPTION_TYPES: OaFieldType[] = ['select', 'radio', 'checkbox']

const PALETTE: { groupKey: string; types: OaFieldType[] }[] = [
  { groupKey: 'input', types: ['text', 'textarea', 'number', 'money', 'date', 'daterange'] },
  { groupKey: 'choice', types: ['select', 'radio', 'checkbox'] },
  { groupKey: 'advanced', types: ['file', 'user'] },
]

// 选中字段按对象引用跟踪：编辑 key 不会丢失选中态
const selectedField = ref<OaField | null>(null)
const previewData = ref<Record<string, unknown>>({})

function onSelect(key: string) {
  selectedField.value = props.fields.find((f) => f.key === key) ?? null
}

function emitChange() {
  emit('update:fields', [...props.fields])
}

function nextKey(type: OaFieldType): string {
  let i = props.fields.length + 1
  let key = `${type}_${i}`
  while (props.fields.some((f) => f.key === key)) key = `${type}_${++i}`
  return key
}

function addField(type: OaFieldType, index?: number) {
  const field: OaField = {
    key: nextKey(type),
    label: t(`oa.fieldType.${type}`),
    type,
    required: false,
  }
  if (OPTION_TYPES.includes(type)) field.options = ['A', 'B']
  const at = index ?? props.fields.length
  props.fields.splice(at, 0, field)
  selectedField.value = field
  emitChange()
}

function onMove(key: string, dir: -1 | 1) {
  const idx = props.fields.findIndex((f) => f.key === key)
  const target = idx + dir
  if (idx < 0 || target < 0 || target >= props.fields.length) return
  const a = props.fields[idx]!
  props.fields[idx] = props.fields[target]!
  props.fields[target] = a
  emitChange()
}

function onRemove(key: string) {
  const idx = props.fields.findIndex((f) => f.key === key)
  if (idx < 0) return
  props.fields.splice(idx, 1)
  if (selectedField.value?.key === key) selectedField.value = null
  emitChange()
}

function onDuplicate(key: string) {
  const idx = props.fields.findIndex((f) => f.key === key)
  if (idx < 0) return
  const src = props.fields[idx]!
  const copy: OaField = { ...src, options: src.options ? [...src.options] : undefined }
  let n = 1
  copy.key = `${src.key}_copy`
  while (props.fields.some((f) => f.key === copy.key)) copy.key = `${src.key}_copy${++n}`
  props.fields.splice(idx + 1, 0, copy)
  selectedField.value = copy
  emitChange()
}

/** 画布拖放落点：面板拖入新字段 或 既有字段拖拽排序 */
function onDropAt(index: number, raw: string) {
  try {
    const data = JSON.parse(raw) as { kind: string; key?: string; fieldType?: OaFieldType }
    if (data.kind === 'palette' && data.fieldType) {
      addField(data.fieldType, index)
      return
    }
    if (data.kind === 'move' && data.key) {
      const from = props.fields.findIndex((f) => f.key === data.key)
      if (from < 0) return
      const [item] = props.fields.splice(from, 1)
      // 从前面挪走一个元素后，落点下标随之前移
      const to = from < index ? index - 1 : index
      props.fields.splice(to, 0, item!)
      selectedField.value = item!
      emitChange()
    }
  } catch {
    /* 非法拖放数据忽略 */
  }
}

function onPaletteDragStart(e: DragEvent, type: OaFieldType) {
  e.dataTransfer?.setData('application/x-oa-field', JSON.stringify({ kind: 'palette', fieldType: type }))
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'copy'
}

function onFieldTypeChange(f: OaField) {
  // 切换为选项类控件时补默认选项（占位值，用户在选项编辑器中改写）
  if (OPTION_TYPES.includes(f.type) && !f.options?.length) f.options = ['A', 'B']
}

/* ---------- 选项编辑器（增删排序） ---------- */
function addOption(f: OaField) {
  f.options = [...(f.options ?? []), '']
}

function removeOption(f: OaField, idx: number) {
  f.options?.splice(idx, 1)
}

function moveOption(f: OaField, idx: number, dir: -1 | 1) {
  const opts = f.options
  if (!opts) return
  const target = idx + dir
  if (target < 0 || target >= opts.length) return
  const a = opts[idx]!
  opts[idx] = opts[target]!
  opts[target] = a
}
</script>

<template>
  <div class="oa-form-designer">
    <div class="ofd-palette">
      <div class="ofd-panel-title">{{ t('oa.design.palette') }}</div>
      <div class="ofd-panel-tip">{{ t('oa.design.paletteHint') }}</div>
      <div class="ofd-palette-scroll">
        <section v-for="g in PALETTE" :key="g.groupKey" class="palette-section">
          <div class="palette-group-title">{{ t(`oa.design.paletteGroup.${g.groupKey}`) }}</div>
          <div class="palette-grid">
            <button
              v-for="ft in g.types"
              :key="ft"
              type="button"
              class="palette-tile"
              draggable="true"
              @click="addField(ft)"
              @dragstart="onPaletteDragStart($event, ft)"
            >
              <span class="palette-tile-icon">{{ t(`oa.fieldType.${ft}`).slice(0, 1) }}</span>
              <span class="palette-tile-label">{{ t(`oa.fieldType.${ft}`) }}</span>
            </button>
          </div>
        </section>
      </div>
    </div>

    <div class="ofd-canvas">
      <div class="ofd-panel-title">{{ t('oa.design.preview') }}</div>
      <div class="ofd-canvas-scroll">
        <div v-if="!props.fields.length" class="canvas-empty">{{ t('oa.design.canvasEmpty') }}</div>
        <FormRenderer
          v-else
          :fields="props.fields"
          v-model="previewData"
          design
          :selected-key="selectedField?.key ?? undefined"
          @select="onSelect"
          @move="onMove"
          @remove="onRemove"
          @duplicate="onDuplicate"
          @drop-at="onDropAt"
        />
      </div>
    </div>

    <div class="ofd-props">
      <div class="ofd-props-head">
        <div class="ofd-panel-title">{{ t('oa.design.props') }}</div>
        <el-button
          v-if="selectedField"
          size="small"
          type="danger"
          plain
          :icon="Delete"
          @click="selectedField && onRemove(selectedField.key)"
        >
          {{ t('oa.design.deleteField') }}
        </el-button>
      </div>
      <div v-if="selectedField" class="ofd-props-scroll">
        <el-form label-position="top" size="small">
          <el-form-item :label="t('oa.design.fieldLabel')">
            <el-input v-model="selectedField.label" />
          </el-form-item>
          <el-form-item :label="t('oa.design.fieldKey')">
            <el-input v-model="selectedField.key" placeholder="leave_type" />
          </el-form-item>
          <el-form-item :label="t('oa.design.fieldType')">
            <el-select
              v-model="selectedField.type"
              style="width: 100%"
              @change="onFieldTypeChange(selectedField)"
            >
              <el-option
                v-for="ft in PALETTE.flatMap((g) => g.types)"
                :key="ft"
                :value="ft"
                :label="t(`oa.fieldType.${ft}`)"
              />
            </el-select>
          </el-form-item>
          <el-form-item :label="t('oa.design.required')">
            <el-switch v-model="selectedField.required" />
          </el-form-item>
          <el-form-item v-if="OPTION_TYPES.includes(selectedField.type)" :label="t('oa.design.options')">
            <div class="options-editor">
              <div v-for="(_o, oi) in selectedField.options ?? []" :key="oi" class="option-row">
                <el-input
                  v-model="selectedField.options![oi]"
                  :placeholder="t('oa.design.optionN', { n: oi + 1 })"
                />
                <el-button size="small" circle :icon="Top" :disabled="oi === 0" @click="moveOption(selectedField, oi, -1)" />
                <el-button
                  size="small"
                  circle
                  :icon="Bottom"
                  :disabled="oi >= (selectedField.options?.length ?? 0) - 1"
                  @click="moveOption(selectedField, oi, 1)"
                />
                <el-button size="small" circle type="danger" plain :icon="Delete" @click="removeOption(selectedField, oi)" />
              </div>
              <el-button size="small" plain type="primary" @click="addOption(selectedField)">
                {{ t('oa.design.optionAdd') }}
              </el-button>
            </div>
          </el-form-item>
          <el-form-item :label="t('oa.design.placeholder')">
            <el-input v-model="selectedField.placeholder" />
          </el-form-item>
          <el-form-item
            v-if="selectedField.type === 'text' || selectedField.type === 'textarea'"
            :label="t('oa.design.maxlength')"
          >
            <el-input-number v-model="selectedField.maxlength" :min="0" :max="5000" />
          </el-form-item>
          <el-form-item :label="t('oa.design.exposeVariable')">
            <el-switch v-model="selectedField.exposeVariable" />
            <div class="prop-tip">{{ t('oa.design.exposeTip') }}</div>
          </el-form-item>
        </el-form>
      </div>
      <div v-else class="props-empty">{{ t('oa.design.propsEmpty') }}</div>
    </div>
  </div>
</template>

<style scoped>
.oa-form-designer {
  display: flex;
  gap: var(--bs-space-3);
  min-height: 460px;
  height: 58vh;
}

.ofd-panel-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
  flex-shrink: 0;
}

.ofd-panel-tip {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  flex-shrink: 0;
}

/* ---------- 左：字段面板 ---------- */
.ofd-palette {
  width: 200px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-lg);
  background: var(--bs-color-bg-surface);
  padding: var(--bs-space-3);
}

.ofd-palette-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.palette-group-title {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  margin-bottom: var(--bs-space-1);
}

.palette-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--bs-space-1);
}

.palette-tile {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: var(--bs-space-2) 2px;
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  cursor: grab;
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-default);
  transition:
    border-color 0.15s,
    background 0.15s;
}

.palette-tile:hover {
  border-color: var(--bs-color-brand-primary);
  background: var(--bs-color-fill-light);
}

.palette-tile:active {
  cursor: grabbing;
}

.palette-tile-icon {
  width: 26px;
  height: 26px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-brand-primary-soft);
  color: var(--bs-color-brand-primary);
  font-weight: 600;
}

/* ---------- 中：画布 ---------- */
.ofd-canvas {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-lg);
  background: var(--bs-color-fill-lighter);
  padding: var(--bs-space-3);
}

.ofd-canvas-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  padding: var(--bs-space-4);
}

.canvas-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 200px;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
  border: 1px dashed var(--bs-color-border-strong);
  border-radius: var(--bs-radius-md);
}

/* ---------- 右：属性 ---------- */
.ofd-props {
  width: 300px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-lg);
  background: var(--bs-color-bg-surface);
  padding: var(--bs-space-3);
}

.ofd-props-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
}

.ofd-props-scroll {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.props-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
  text-align: center;
  padding: 0 var(--bs-space-3);
}

.options-editor {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-1);
  align-items: flex-start;
}

.option-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 4px;
}

.option-row .el-button + .el-button {
  margin-left: 0;
}

.prop-tip {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  line-height: 1.4;
}
</style>
