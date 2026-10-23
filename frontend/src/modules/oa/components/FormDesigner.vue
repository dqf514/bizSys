<script setup lang="ts">
/** OA 表单设计器（复刻 TPCworkflow FormDesigner 三栏交互，数据模型保持 bizSys fields[]）。
 * 左：字段类型面板（点击或拖拽添加，含资源/布局控件）；中：画布（FormRenderer 设计模式实时预览，
 * 点击选中 / 拖拽排序 / 复制 / 删除）；右：字段属性（基础/选项/级联/条件逻辑/资源映射）。
 * 布局控件（divider/text_block）key 自动生成仅占位，不产生表单数据。
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { Bottom, Delete, Plus, Top } from '@element-plus/icons-vue'
import FormRenderer from './FormRenderer.vue'
import ConditionEditor from './ConditionEditor.vue'
import type {
  OaField,
  OaFieldMapping,
  OaFieldType,
  OaResourceMeta,
  OaResourceType,
} from '@/api/types'
import { listOaResourceMeta } from '@/api/oa'
import { dictTypes } from '@/api/admin'

const props = defineProps<{ fields: OaField[] }>()
const emit = defineEmits<{ (e: 'update:fields', v: OaField[]): void }>()

const { t } = useI18n()

const OPTION_TYPES: OaFieldType[] = ['select', 'radio', 'checkbox']
const LAYOUT_TYPES: OaFieldType[] = ['divider', 'text_block']
const CASCADABLE_TYPES: OaFieldType[] = ['select', 'radio']
const EXPOSABLE_TYPES: OaFieldType[] = ['text', 'number', 'money', 'date', 'select', 'radio', 'user']

const PALETTE: { groupKey: string; types: OaFieldType[] }[] = [
  { groupKey: 'input', types: ['text', 'textarea', 'number', 'money', 'date', 'daterange'] },
  { groupKey: 'choice', types: ['select', 'radio', 'checkbox'] },
  { groupKey: 'advanced', types: ['file', 'user', 'resource'] },
  { groupKey: 'layout', types: ['divider', 'text_block'] },
]

// 选中字段按对象引用跟踪：编辑 key 不会丢失选中态
const selectedField = ref<OaField | null>(null)
const previewData = ref<Record<string, unknown>>({})

const isLayout = computed(() => selectedField.value != null && LAYOUT_TYPES.includes(selectedField.value.type))
const isOptionType = computed(
  () => selectedField.value != null && OPTION_TYPES.includes(selectedField.value.type),
)
const isResource = computed(() => selectedField.value?.type === 'resource')

/** 可被条件/级联/映射引用的数据控件（排除布局与自身） */
const candidateFields = computed(() =>
  props.fields.filter((f) => !LAYOUT_TYPES.includes(f.type) && f.key && f !== selectedField.value),
)

/** 级联父控件候选：手工选项的 select/radio */
const cascadeParents = computed(() =>
  candidateFields.value.filter(
    (f) => CASCADABLE_TYPES.includes(f.type) && (f.optionsSource ?? 'manual') === 'manual' && f.options?.length,
  ),
)

const cascadeParentField = computed(() =>
  props.fields.find((f) => f.key === selectedField.value?.cascade?.parent),
)

/* ---------- 资源元数据 / 字典类型（设计器配置数据源） ---------- */
const resourceMeta = ref<OaResourceMeta[]>([])
const dictTypeOptions = ref<{ code: string; name: string }[]>([])

onMounted(async () => {
  try {
    resourceMeta.value = await listOaResourceMeta()
  } catch {
    resourceMeta.value = []
  }
  try {
    dictTypeOptions.value = (await dictTypes()).map((d) => ({ code: d.code, name: d.name }))
  } catch {
    dictTypeOptions.value = [] // no dict permission: fall back to free input (allow-create)
  }
})

const mappingFromOptions = computed(
  () => resourceMeta.value.find((m) => m.type === selectedField.value?.resource)?.fields ?? [],
)

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
  if (type === 'resource') field.mappings = []
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
  const copy: OaField = {
    ...src,
    options: src.options ? [...src.options] : undefined,
    mappings: src.mappings ? src.mappings.map((m) => ({ ...m })) : undefined,
    cascade: src.cascade ? { parent: src.cascade.parent, map: { ...src.cascade.map } } : undefined,
    showWhen: src.showWhen ? structuredClone(src.showWhen) : undefined,
    requiredWhen: src.requiredWhen ? structuredClone(src.requiredWhen) : undefined,
    readonlyWhen: src.readonlyWhen ? structuredClone(src.readonlyWhen) : undefined,
  }
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
  if (OPTION_TYPES.includes(f.type) && (f.optionsSource ?? 'manual') === 'manual' && !f.options?.length) {
    f.options = ['A', 'B']
  }
  if (f.type === 'resource' && !f.mappings) f.mappings = []
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

/* ---------- 级联 ---------- */
const cascadeEnabled = computed({
  get: () => Boolean(selectedField.value?.cascade),
  set: (on: boolean) => {
    const f = selectedField.value
    if (!f) return
    f.cascade = on ? { parent: '', map: {} } : null
  },
})

function cascadeMapValues(opt: string): string[] {
  return selectedField.value?.cascade?.map?.[opt] ?? []
}

function setCascadeMap(opt: string, values: string[]) {
  const f = selectedField.value
  if (!f?.cascade) return
  f.cascade = { ...f.cascade, map: { ...f.cascade.map, [opt]: values } }
}

/* ---------- 资源映射 ---------- */
function addMapping(f: OaField) {
  f.mappings = [...(f.mappings ?? []), { from: '', to: '' }]
}

function removeMapping(f: OaField, idx: number) {
  f.mappings?.splice(idx, 1)
}

function patchMapping(f: OaField, idx: number, patch: Partial<OaFieldMapping>) {
  if (!f.mappings) return
  f.mappings = f.mappings.map((m, i) => (i === idx ? { ...m, ...patch } : m))
}

function onResourceTypeChange(f: OaField) {
  // 换资源类型后映射来源失效，清空重配
  f.mappings = []
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
          <template v-if="isLayout">
            <div class="prop-tip">{{ t('oa.design.layoutTip') }}</div>
          </template>
          <template v-else>
            <el-form-item :label="t('oa.design.fieldKey')">
              <el-input v-model="selectedField.key" placeholder="leave_type" />
            </el-form-item>
          </template>
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
          <el-form-item :label="t('oa.design.span')">
            <el-radio-group :model-value="selectedField.span ?? 24" @update:model-value="selectedField!.span = $event === 12 ? 12 : null">
              <el-radio-button :value="24">{{ t('oa.design.spanFull') }}</el-radio-button>
              <el-radio-button :value="12">{{ t('oa.design.spanHalf') }}</el-radio-button>
            </el-radio-group>
          </el-form-item>
          <template v-if="!isLayout">
            <el-form-item :label="t('oa.design.required')">
              <el-switch v-model="selectedField.required" />
            </el-form-item>
            <el-form-item :label="t('oa.design.placeholder')">
              <el-input v-model="selectedField.placeholder" />
            </el-form-item>
          </template>
          <el-form-item :label="t('oa.design.fieldDescription')">
            <el-input v-model="selectedField.description" />
          </el-form-item>
          <el-form-item
            v-if="['text', 'textarea', 'select'].includes(selectedField.type)"
            :label="t('oa.design.defaultValue')"
          >
            <el-input :model-value="(selectedField.defaultValue as string) ?? ''" @update:model-value="selectedField!.defaultValue = $event" />
          </el-form-item>
          <el-form-item
            v-else-if="['number', 'money'].includes(selectedField.type)"
            :label="t('oa.design.defaultValue')"
          >
            <el-input-number
              :model-value="(selectedField.defaultValue as number) ?? undefined"
              controls-position="right"
              @update:model-value="selectedField!.defaultValue = $event ?? null"
            />
          </el-form-item>
          <el-form-item
            v-if="selectedField.type === 'text' || selectedField.type === 'textarea'"
            :label="t('oa.design.maxlength')"
          >
            <el-input-number v-model="selectedField.maxlength" :min="0" :max="5000" />
          </el-form-item>
          <el-form-item v-if="EXPOSABLE_TYPES.includes(selectedField.type)" :label="t('oa.design.exposeVariable')">
            <el-switch v-model="selectedField.exposeVariable" />
            <div class="prop-tip">{{ t('oa.design.exposeTip') }}</div>
          </el-form-item>

          <!-- 选项：手工 / 字典数据源 -->
          <template v-if="isOptionType">
            <el-form-item :label="t('oa.design.optionsSource')">
              <el-radio-group
                :model-value="selectedField.optionsSource ?? 'manual'"
                @update:model-value="selectedField!.optionsSource = $event as 'manual' | 'dict'"
              >
                <el-radio-button value="manual">{{ t('oa.design.optionsSourceManual') }}</el-radio-button>
                <el-radio-button value="dict">{{ t('oa.design.optionsSourceDict') }}</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item v-if="(selectedField.optionsSource ?? 'manual') === 'dict'" :label="t('oa.design.dictType')">
              <el-select
                v-model="selectedField.dictType"
                filterable
                allow-create
                default-first-option
                style="width: 100%"
                :placeholder="t('oa.design.dictTypeTip')"
              >
                <el-option v-for="d in dictTypeOptions" :key="d.code" :value="d.code" :label="`${d.name} (${d.code})`" />
              </el-select>
            </el-form-item>
            <el-form-item v-else :label="t('oa.design.options')">
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

            <!-- 级联过滤 -->
            <el-form-item v-if="CASCADABLE_TYPES.includes(selectedField.type) && (selectedField.optionsSource ?? 'manual') === 'manual'" :label="t('oa.design.cascade')">
              <div class="cascade-editor">
                <div class="cascade-head">
                  <span class="prop-tip">{{ t('oa.design.cascadeEnable') }}</span>
                  <el-switch :model-value="cascadeEnabled" @update:model-value="cascadeEnabled = Boolean($event)" />
                </div>
                <template v-if="selectedField.cascade">
                  <el-select
                    :model-value="selectedField.cascade.parent"
                    :placeholder="t('oa.design.cascadeParent')"
                    style="width: 100%"
                    @update:model-value="selectedField!.cascade = { parent: String($event ?? ''), map: {} }"
                  >
                    <el-option
                      v-for="p in cascadeParents"
                      :key="p.key"
                      :value="p.key"
                      :label="p.label || p.key"
                    />
                  </el-select>
                  <template v-if="cascadeParentField?.options?.length">
                    <div v-for="opt in cascadeParentField.options" :key="opt" class="cascade-row">
                      <span class="cascade-opt" :title="opt">{{ opt }}</span>
                      <el-select
                        :model-value="cascadeMapValues(opt)"
                        multiple
                        collapse-tags
                        style="flex: 1; min-width: 0"
                        @update:model-value="setCascadeMap(opt, $event as string[])"
                      >
                        <el-option v-for="o in selectedField.options ?? []" :key="o" :value="o" :label="o" />
                      </el-select>
                    </div>
                  </template>
                  <div v-else class="prop-tip">{{ t('oa.design.cascadeMapEmpty') }}</div>
                </template>
              </div>
            </el-form-item>
          </template>

          <!-- 资源控件 -->
          <template v-if="isResource">
            <el-form-item :label="t('oa.design.resourceType')">
              <el-select
                :model-value="selectedField.resource || ''"
                style="width: 100%"
                @update:model-value="selectedField!.resource = $event as OaResourceType; onResourceTypeChange(selectedField!)"
              >
                <el-option v-for="m in resourceMeta" :key="m.type" :value="m.type" :label="m.label" />
              </el-select>
              <div class="prop-tip">{{ t('oa.design.resourceTypeTip') }}</div>
            </el-form-item>
            <el-form-item :label="t('oa.design.mappings')">
              <div class="mappings-editor">
                <div v-for="(_m, mi) in selectedField.mappings ?? []" :key="mi" class="mapping-row">
                  <el-select
                    :model-value="selectedField.mappings![mi]!.from"
                    :placeholder="t('oa.design.mappingFrom')"
                    filterable
                    @update:model-value="patchMapping(selectedField!, mi, { from: String($event ?? '') })"
                  >
                    <el-option v-for="o in mappingFromOptions" :key="o.key" :value="o.key" :label="o.label" />
                  </el-select>
                  <el-select
                    :model-value="selectedField.mappings![mi]!.to"
                    :placeholder="t('oa.design.mappingTo')"
                    filterable
                    @update:model-value="patchMapping(selectedField!, mi, { to: String($event ?? '') })"
                  >
                    <el-option
                      v-for="tf in candidateFields"
                      :key="tf.key"
                      :value="tf.key"
                      :label="tf.label || tf.key"
                    />
                  </el-select>
                  <el-button size="small" circle type="danger" plain :icon="Delete" @click="removeMapping(selectedField, mi)" />
                </div>
                <el-button size="small" plain :icon="Plus" @click="addMapping(selectedField)">
                  {{ t('oa.design.mappingAdd') }}
                </el-button>
              </div>
            </el-form-item>
          </template>

          <!-- 条件逻辑 -->
          <template v-if="!isLayout">
            <el-form-item>
              <ConditionEditor
                :model-value="selectedField.showWhen"
                :fields="candidateFields"
                :title="t('oa.design.condShow')"
                @update:model-value="selectedField!.showWhen = $event"
              />
            </el-form-item>
            <el-form-item>
              <ConditionEditor
                :model-value="selectedField.requiredWhen"
                :fields="candidateFields"
                :title="t('oa.design.condRequired')"
                @update:model-value="selectedField!.requiredWhen = $event"
              />
            </el-form-item>
            <el-form-item>
              <ConditionEditor
                :model-value="selectedField.readonlyWhen"
                :fields="candidateFields"
                :title="t('oa.design.condReadonly')"
                @update:model-value="selectedField!.readonlyWhen = $event"
              />
            </el-form-item>
          </template>
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
  width: 320px;
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

.cascade-editor,
.mappings-editor {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  align-items: flex-start;
}

.cascade-head {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.cascade-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.cascade-opt {
  flex: 0 0 64px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.mapping-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 4px;
}

.mapping-row .el-select {
  flex: 1;
  min-width: 0;
}

.prop-tip {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  line-height: 1.4;
}
</style>
