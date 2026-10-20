<script setup lang="ts">
/** OA 动态表单渲染器：按表单 schema 渲染控件，disabled 时为只读回显。
 * file 字段暂无通用上传通道，占位为附件 URL 列表编辑；user 字段用人员下拉（接口不可用时降级为 ID 输入）。
 * design 模式（表单设计器画布）：字段外层包裹可选中/可拖放容器，
 * 发出 select/move/remove/duplicate/drop-at 事件，渲染逻辑与运行时完全一致。
 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import type { FormInstance } from 'element-plus'
import { Bottom, CopyDocument, Delete, Rank, Top } from '@element-plus/icons-vue'
import type { OaField } from '@/api/types'
import { listUsers } from '@/api/admin'

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

function setVal(key: string, v: unknown) {
  emit('update:modelValue', { ...props.modelValue, [key]: v })
}

function val(key: string): unknown {
  return props.modelValue?.[key]
}

const rules = computed(() => {
  const r: Record<string, { required: boolean; message: string; trigger: string }[]> = {}
  for (const f of props.fields) {
    if (f.required) r[f.key] = [{ required: true, message: t('common.form.required'), trigger: 'change' }]
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
    const data = await listUsers({ page: 1, size: 200 })
    userOptions.value = (data.items ?? []).map((u) => ({ id: u.id, name: u.name || u.username }))
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
  <el-form ref="formRef" :model="props.modelValue" :rules="rules" label-width="110px" :disabled="props.disabled">
    <div
      v-for="(f, fi) in props.fields"
      :key="f.key"
      class="fr-item"
      :class="{
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
      <el-form-item :label="f.label" :prop="f.key">
        <el-input
          v-if="f.type === 'text'"
          :model-value="(val(f.key) as string) ?? ''"
          :placeholder="f.placeholder"
          :maxlength="f.maxlength ?? undefined"
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
          show-word-limit
          style="width: 100%"
          @update:model-value="setVal(f.key, $event)"
        />
        <el-input-number
          v-else-if="f.type === 'number'"
          :model-value="(val(f.key) as number) ?? undefined"
          controls-position="right"
          style="width: 220px"
          @update:model-value="setVal(f.key, $event)"
        />
        <el-input-number
          v-else-if="f.type === 'money'"
          :model-value="(val(f.key) as number) ?? undefined"
          :precision="2"
          :min="0"
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
          @update:model-value="setVal(f.key, $event)"
        />
        <el-date-picker
          v-else-if="f.type === 'daterange'"
          :model-value="(val(f.key) as [string, string]) ?? []"
          type="daterange"
          value-format="YYYY-MM-DD"
          style="width: 320px"
          @update:model-value="setVal(f.key, $event)"
        />
        <el-select
          v-else-if="f.type === 'select'"
          :model-value="(val(f.key) as string) ?? ''"
          :placeholder="f.placeholder || t('common.form.placeholderSelect')"
          clearable
          style="width: 100%"
          @update:model-value="setVal(f.key, $event)"
        >
          <el-option v-for="o in f.options ?? []" :key="o" :label="o" :value="o" />
        </el-select>
        <el-radio-group
          v-else-if="f.type === 'radio'"
          :model-value="(val(f.key) as string) ?? ''"
          @update:model-value="setVal(f.key, $event)"
        >
          <el-radio v-for="o in f.options ?? []" :key="o" :value="o">{{ o }}</el-radio>
        </el-radio-group>
        <el-checkbox-group
          v-else-if="f.type === 'checkbox'"
          :model-value="(val(f.key) as string[]) ?? []"
          @update:model-value="setVal(f.key, $event)"
        >
          <el-checkbox v-for="o in f.options ?? []" :key="o" :value="o">{{ o }}</el-checkbox>
        </el-checkbox-group>
        <div v-else-if="f.type === 'file'" class="file-editor">
          <div v-for="(u, idx) in fileList(f.key)" :key="idx" class="file-row">
            <el-input
              :model-value="u"
              :placeholder="t('oa.form.fileUrlPlaceholder')"
              @update:model-value="setFileRow(f.key, idx, String($event))"
            />
            <el-button v-if="!props.disabled" link type="danger" @click="removeFileRow(f.key, idx)">
              {{ t('common.action.delete') }}
            </el-button>
          </div>
          <el-button v-if="!props.disabled" size="small" plain @click="addFileRow(f.key)">
            {{ t('oa.form.addFileUrl') }}
          </el-button>
        </div>
        <el-select
          v-else-if="f.type === 'user' && !userLoadFailed"
          :model-value="(val(f.key) as number) ?? null"
          filterable
          clearable
          :placeholder="f.placeholder || t('common.form.placeholderSelect')"
          style="width: 100%"
          @update:model-value="setVal(f.key, $event)"
        >
          <el-option v-for="u in userOptions" :key="u.id" :label="u.name" :value="u.id" />
        </el-select>
        <el-input-number
          v-else-if="f.type === 'user'"
          :model-value="(val(f.key) as number) ?? undefined"
          :min="1"
          controls-position="right"
          style="width: 220px"
          @update:model-value="setVal(f.key, $event)"
        />
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
.fr-item {
  position: relative;
}

.fr-design {
  border: 1px dashed transparent;
  border-radius: var(--bs-radius-md);
  padding: 2px var(--bs-space-2) 2px var(--bs-space-6, 24px);
  margin: 0 calc(-1 * var(--bs-space-2));
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
  height: 14px;
  border-radius: var(--bs-radius-sm);
}

.fr-tail.fr-drop {
  box-shadow: inset 0 2px 0 var(--bs-color-brand-primary);
}
</style>
