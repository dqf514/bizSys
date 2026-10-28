<script setup lang="ts">
/** OA 动态表单渲染器：按表单 schema 渲染控件，disabled 时为只读回显。
 * 运行时真实求值：showWhen 隐藏（v-if）/ requiredWhen 进校验规则 / readonlyWhen 禁用；
 * optionsSource=dict 加载字典选项；cascade 按父值过滤并在父值变化时清理失效子值；
 * resource 控件弹窗检索，选中后按 mappings 带出字段；divider/text_block 为布局控件（不占数据位）。
 * design 模式（表单设计器画布）：字段全部可见，外层包裹可选中/可拖放容器，
 * 发出 select/move/remove/duplicate/drop-at 事件，渲染逻辑与运行时一致。
 */
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FormInstance } from 'element-plus'
import { Bottom, CopyDocument, Delete, Rank, Top } from '@element-plus/icons-vue'
import type { OaField, OaResourceItem, OaResourceValue } from '@/api/types'
import { userOptions as fetchUserOptions } from '@/api/admin'
import { useDict } from '@/composables/useDict'
import { isEmptyValue, isFieldReadonly, isFieldRequired, isFieldVisible } from '../formLogic'
import ResourcePicker from './ResourcePicker.vue'

const props = defineProps<{
  fields: OaField[]
  modelValue: Record<string, unknown>
  disabled?: boolean
  /** 设计器画布模式：字段可选中、可拖放排序/接收面板拖入 */
  design?: boolean
  selectedKey?: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: Record<string, unknown>): void
  (e: 'select', key: string): void
  (e: 'move', key: string, dir: -1 | 1): void
  (e: 'remove', key: string): void
  (e: 'duplicate', key: string): void
  (e: 'drop-at', index: number, raw: string): void
}>()

const { t } = useI18n()
const formRef = ref<FormInstance>()

const LAYOUT_TYPES = ['divider', 'text_block']

function isLayout(f: OaField): boolean {
  return LAYOUT_TYPES.includes(f.type)
}

/* ---------- 条件求值（design 模式全部可见/可编辑） ---------- */
function visibleOf(f: OaField): boolean {
  if (props.design) return true
  return isFieldVisible(f, props.modelValue)
}

function requiredOf(f: OaField): boolean {
  if (props.design) return Boolean(f.required)
  return isFieldRequired(f, props.modelValue)
}

function readonlyOf(f: OaField): boolean {
  if (props.design) return false
  return isFieldReadonly(f, props.modelValue)
}

/* ---------- 选项：手工 / 字典 / 级联 ---------- */
const { options: loadDictOptions } = useDict()
const dictOpts = ref<Record<string, { label: string; value: string }[]>>({})

const dictTypesUsed = computed(() => [
  ...new Set(props.fields.filter((f) => f.optionsSource === 'dict' && f.dictType).map((f) => f.dictType!)),
])

async function loadDicts() {
  for (const type of dictTypesUsed.value) {
    if (!(type in dictOpts.value)) dictOpts.value[type] = await loadDictOptions(type)
  }
}

onMounted(loadDicts)
watch(dictTypesUsed, loadDicts)

interface Opt {
  label: string
  value: string
}

/** 当前可选选项（label/value 对）：dict 源取字典；cascade 按父值过滤，父值不在 map 回退全选项。 */
function optionsOf(f: OaField, data?: Record<string, unknown>): Opt[] {
  const base: Opt[] =
    f.optionsSource === 'dict'
      ? (dictOpts.value[f.dictType ?? ''] ?? [])
      : (f.options ?? []).map((o) => ({ label: o, value: o }))
  const cascade = f.cascade
  if (cascade?.parent && cascade.map) {
    const pv = (data ?? props.modelValue)[cascade.parent]
    const key = pv === null || pv === undefined ? '' : String(pv)
    const allowed = cascade.map[key]
    if (Array.isArray(allowed)) return allowed.map((o) => ({ label: o, value: o }))
  }
  return base
}

function setVal(key: string, v: unknown) {
  const next: Record<string, unknown> = { ...props.modelValue, [key]: v }
  // 级联：父值变化时清理不再合法的子控件值
  for (const f of props.fields) {
    if (f.cascade?.parent !== key || !f.key || isEmptyValue(next[f.key])) continue
    const allowed = optionsOf(f, next).map((o) => o.value)
    if (f.type === 'checkbox' && Array.isArray(next[f.key])) {
      next[f.key] = (next[f.key] as unknown[]).filter((x) => allowed.includes(String(x)))
    } else if (!allowed.includes(String(next[f.key]))) {
      next[f.key] = ''
    }
  }
  emit('update:modelValue', next)
}

function val(key: string): unknown {
  return props.modelValue?.[key]
}

/* ---------- 资源控件：选中后按 mappings 带出 ---------- */
function onResourcePick(f: OaField, item: OaResourceItem | null) {
  const next: Record<string, unknown> = {
    ...props.modelValue,
    [f.key]: item ? { id: item.id, name: item.label } : null,
  }
  for (const m of f.mappings ?? []) {
    if (!m.to) continue
    next[m.to] = item ? (item.fields?.[m.from] ?? '') : ''
  }
  emit('update:modelValue', next)
}

const rules = computed(() => {
  const r: Record<string, { required: boolean; message: string; trigger: string }[]> = {}
  for (const f of props.fields) {
    if (isLayout(f) || !f.key) continue
    if (!props.design && !visibleOf(f)) continue
    if (requiredOf(f)) r[f.key] = [{ required: true, message: t('common.form.required'), trigger: 'change' }]
  }
  return r
})

/* user 字段人员选项（无权限时降级为 ID 输入） */
const userOptions = ref<{ id: number; name: string }[]>([])
const userLoadFailed = ref(false)
const hasUserField = computed(() => props.fields.some((f) => f.type === 'user'))

onMounted(async () => {
  if (!hasUserField.value) return
  try {
    // 轻量选人端点（登录可用）：OA 填写人通常无 admin:user:list
    const data = await fetchUserOptions()
    userOptions.value = (data ?? []).map((u) => ({ id: u.id, name: u.label }))
  } catch {
    userLoadFailed.value = true
  }
})

/* file 字段：URL 列表编辑（占位实现） */
function fileList(key: string): string[] {
  const v = val(key)
  return Array.isArray(v) ? (v as string[]) : []
}

function setFileRow(key: string, idx: number, v: string) {
  const list = [...fileList(key)]
  list[idx] = v
  setVal(key, list)
}

function addFileRow(key: string) {
  setVal(key, [...fileList(key), ''])
}

function removeFileRow(key: string, idx: number) {
  setVal(key, fileList(key).filter((_, i) => i !== idx))
}

/* ---------- 设计模式：拖放 ---------- */
const dropIdx = ref<number | null>(null)

function onHandleDragStart(e: DragEvent, key: string) {
  e.dataTransfer?.setData('application/x-oa-field', JSON.stringify({ kind: 'move', key }))
  e.dataTransfer?.setData('text/plain', key)
  if (e.dataTransfer) e.dataTransfer.effectAllowed = 'move'
}

function onDragOver(e: DragEvent, idx: number) {
  if (!e.dataTransfer) return
  e.preventDefault()
  e.dataTransfer.dropEffect = 'move'
  dropIdx.value = idx
}

function onDrop(e: DragEvent, idx: number) {
  e.preventDefault()
  const raw = e.dataTransfer?.getData('application/x-oa-field') ?? ''
  dropIdx.value = null
  if (raw) emit('drop-at', idx, raw)
}

async function validate(): Promise<boolean> {
  if (!formRef.value) return true
  return formRef.value.validate().catch(() => false)
}

defineExpose({ validate })
</script>

<template>
  <el-form
    ref="formRef"
    :model="props.modelValue"
    :rules="rules"
    label-width="110px"
    :disabled="props.disabled"
    class="fr-form"
  >
    <div
      v-for="(f, fi) in props.fields"
      v-show="visibleOf(f)"
      :key="f.key || `__layout_${fi}`"
      class="fr-item"
      :class="{
        'fr-half': f.span === 12,
        'fr-design': props.design,
        'fr-active': props.design && props.selectedKey === f.key,
        'fr-drop': props.design && dropIdx === fi,
      }"
      @click="props.design && emit('select', f.key)"
      @dragover="props.design && onDragOver($event, fi)"
      @dragleave="props.design && (dropIdx = null)"
      @drop="props.design && onDrop($event, fi)"
    >
      <span
        v-if="props.design"
        class="fr-handle"
        draggable="true"
        :title="t('oa.design.dragSortTip')"
        @dragstart="onHandleDragStart($event, f.key)"
        @dragend="dropIdx = null"
      >
        <el-icon><Rank /></el-icon>
      </span>
      <div v-if="props.design && props.selectedKey === f.key" class="fr-actions" @click.stop>
        <el-button size="small" circle :icon="Top" @click="emit('move', f.key, -1)" />
        <el-button size="small" circle :icon="Bottom" @click="emit('move', f.key, 1)" />
        <el-button size="small" circle :icon="CopyDocument" @click="emit('duplicate', f.key)" />
        <el-button size="small" circle type="danger" plain :icon="Delete" @click="emit('remove', f.key)" />
      </div>

      <!-- 布局控件：不占数据位 -->
      <el-divider v-if="f.type === 'divider'" content-position="left" class="fr-divider">{{ f.label }}</el-divider>
      <div v-else-if="f.type === 'text_block'" class="fr-text-block">{{ f.label }}</div>

      <el-form-item v-else :label="f.label" :prop="f.key">
        <el-input
          v-if="f.type === 'text'"
          :model-value="(val(f.key) as string) ?? ''"
          :placeholder="f.placeholder"
          :maxlength="f.maxlength ?? undefined"
          :disabled="readonlyOf(f)"
          style="width: 100%"
          @update:model-value="setVal(f.key, $event)"
        />
        <el-input
          v-else-if="f.type === 'textarea'"
          :model-value="(val(f.key) as string) ?? ''"
          type="textarea"
          :rows="3"
          :placeholder="f.placeholder"
          :maxlength="f.maxlength ?? undefined"
          :disabled="readonlyOf(f)"
          show-word-limit
          style="width: 100%"
          @update:model-value="setVal(f.key, $event)"
        />
        <el-input-number
          v-else-if="f.type === 'number'"
          :model-value="(val(f.key) as number) ?? undefined"
          :disabled="readonlyOf(f)"
          controls-position="right"
          style="width: 220px"
          @update:model-value="setVal(f.key, $event)"
        />
        <el-input-number
          v-else-if="f.type === 'money'"
          :model-value="(val(f.key) as number) ?? undefined"
          :precision="2"
          :min="0"
          :disabled="readonlyOf(f)"
          controls-position="right"
          style="width: 220px"
          @update:model-value="setVal(f.key, $event)"
        />
        <el-date-picker
          v-else-if="f.type === 'date'"
          :model-value="(val(f.key) as string) ?? ''"
          type="date"
          value-format="YYYY-MM-DD"
          :placeholder="f.placeholder || t('common.form.placeholderSelect')"
          :disabled="readonlyOf(f)"
          @update:model-value="setVal(f.key, $event)"
        />
        <el-date-picker
          v-else-if="f.type === 'daterange'"
          :model-value="(val(f.key) as [string, string]) ?? []"
          type="daterange"
          value-format="YYYY-MM-DD"
          :disabled="readonlyOf(f)"
          style="width: 320px"
          @update:model-value="setVal(f.key, $event)"
        />
        <el-select
          v-else-if="f.type === 'select'"
          :model-value="(val(f.key) as string) ?? ''"
          :placeholder="f.placeholder || t('common.form.placeholderSelect')"
          :disabled="readonlyOf(f)"
          clearable
          style="width: 100%"
          @update:model-value="setVal(f.key, $event)"
        >
          <el-option v-for="o in optionsOf(f)" :key="o.value" :label="o.label" :value="o.value" />
        </el-select>
        <el-radio-group
          v-else-if="f.type === 'radio'"
          :model-value="(val(f.key) as string) ?? ''"
          :disabled="readonlyOf(f)"
          @update:model-value="setVal(f.key, $event)"
        >
          <el-radio v-for="o in optionsOf(f)" :key="o.value" :value="o.value">{{ o.label }}</el-radio>
        </el-radio-group>
        <el-checkbox-group
          v-else-if="f.type === 'checkbox'"
          :model-value="(val(f.key) as string[]) ?? []"
          :disabled="readonlyOf(f)"
          @update:model-value="setVal(f.key, $event)"
        >
          <el-checkbox v-for="o in optionsOf(f)" :key="o.value" :value="o.value">{{ o.label }}</el-checkbox>
        </el-checkbox-group>
        <div v-else-if="f.type === 'file'" class="file-editor">
          <div v-for="(u, idx) in fileList(f.key)" :key="idx" class="file-row">
            <el-input
              :model-value="u"
              :placeholder="t('oa.form.fileUrlPlaceholder')"
              :disabled="readonlyOf(f)"
              @update:model-value="setFileRow(f.key, idx, String($event))"
            />
            <el-button v-if="!props.disabled && !readonlyOf(f)" link type="danger" @click="removeFileRow(f.key, idx)">
              {{ t('common.action.delete') }}
            </el-button>
          </div>
          <el-button v-if="!props.disabled && !readonlyOf(f)" size="small" plain @click="addFileRow(f.key)">
            {{ t('oa.form.addFileUrl') }}
          </el-button>
        </div>
        <el-select
          v-else-if="f.type === 'user' && !userLoadFailed"
          :model-value="(val(f.key) as number) ?? null"
          filterable
          clearable
          :placeholder="f.placeholder || t('common.form.placeholderSelect')"
          :disabled="readonlyOf(f)"
          style="width: 100%"
          @update:model-value="setVal(f.key, $event)"
        >
          <el-option v-for="u in userOptions" :key="u.id" :label="u.name" :value="u.id" />
        </el-select>
        <el-input-number
          v-else-if="f.type === 'user'"
          :model-value="(val(f.key) as number) ?? undefined"
          :min="1"
          :disabled="readonlyOf(f)"
          controls-position="right"
          style="width: 220px"
          @update:model-value="setVal(f.key, $event)"
        />
        <ResourcePicker
          v-else-if="f.type === 'resource'"
          :model-value="(val(f.key) as OaResourceValue) ?? null"
          :resource="f.resource ?? ''"
          :placeholder="f.placeholder"
          :disabled="props.disabled || readonlyOf(f)"
          @update:model-value="setVal(f.key, $event)"
          @pick="onResourcePick(f, $event)"
        />
        <div v-if="f.description" class="fr-desc">{{ f.description }}</div>
      </el-form-item>
    </div>
    <div
      v-if="props.design"
      class="fr-tail"
      :class="{ 'fr-drop': dropIdx === props.fields.length }"
      @dragover="props.design && onDragOver($event, props.fields.length)"
      @dragleave="props.design && (dropIdx = null)"
      @drop="props.design && onDrop($event, props.fields.length)"
    />
  </el-form>
</template>

<style scoped>
.fr-form {
  display: flex;
  flex-wrap: wrap;
  column-gap: var(--bs-space-4);
}

.fr-item {
  position: relative;
  flex: 0 0 100%;
}

.fr-item.fr-half {
  flex: 0 0 calc(50% - var(--bs-space-2));
}

/* 移动端：双列表单项降为单列 */
@media (max-width: 767px) {
  .fr-item.fr-half {
    flex: 0 0 100%;
  }
}

.fr-divider {
  margin: var(--bs-space-2) 0 var(--bs-space-4);
}

.fr-text-block {
  padding: var(--bs-space-2) 0 var(--bs-space-3);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
  line-height: 1.6;
  white-space: pre-wrap;
}

.fr-desc {
  width: 100%;
  margin-top: 2px;
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  line-height: 1.4;
}

.file-editor {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.file-row {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

/* ---------- 设计模式 ---------- */
.fr-design {
  border: 1px dashed transparent;
  border-radius: var(--bs-radius-md);
  padding: 2px var(--bs-space-2) 2px var(--bs-space-6, 24px);
  cursor: pointer;
  transition:
    border-color 0.15s,
    background 0.15s;
}

.fr-design:hover {
  border-color: var(--bs-color-border-strong);
}

.fr-design.fr-active {
  border-color: var(--bs-color-brand-primary);
  background: var(--bs-color-brand-primary-soft);
}

.fr-design.fr-drop {
  border-color: var(--bs-color-brand-primary);
  box-shadow: inset 0 2px 0 var(--bs-color-brand-primary);
}

.fr-handle {
  position: absolute;
  left: 4px;
  top: 10px;
  display: inline-flex;
  align-items: center;
  color: var(--bs-color-fg-muted);
  cursor: grab;
  font-size: 13px;
}

.fr-handle:active {
  cursor: grabbing;
}

.fr-actions {
  position: absolute;
  right: 6px;
  top: -12px;
  z-index: 2;
  display: flex;
  gap: 4px;
  padding: 2px;
  border-radius: var(--bs-radius-full);
  background: var(--bs-color-bg-elevated);
  box-shadow: var(--bs-shadow-elevation2);
}

.fr-actions .el-button + .el-button {
  margin-left: 0;
}

.fr-tail {
  flex: 0 0 100%;
  height: 14px;
  border-radius: var(--bs-radius-sm);
}

.fr-tail.fr-drop {
  box-shadow: inset 0 2px 0 var(--bs-color-brand-primary);
}
</style>
