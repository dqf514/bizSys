<script setup lang="ts">
/** OA 表单设计（统一流程设计页的第二页签）：表单列表 + 新建/编辑弹窗（基本属性 + 字段设计器 + 实时预览 + 绑定流程）。
 * 绑定流程下拉右侧"去设计" → emit('goto-def', flowDefinitionId)，由 FlowDefList 切回流程定义页签并打开编辑。
 */
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import FormRenderer from '@/modules/oa/components/FormRenderer.vue'
import { useDict } from '@/composables/useDict'
import {
  createOaForm,
  deleteOaForm,
  disableOaForm,
  listOaFlowDefs,
  listOaForms,
  newOaFormVersion,
  publishOaForm,
  updateOaForm,
  type OaFormPayload,
} from '@/api/oa'
import type { OaField, OaFieldType, OaFlowDefOption, OaForm } from '@/api/types'

defineOptions({ name: 'OaFormPanel' })

const emit = defineEmits<{ (e: 'goto-def', flowDefinitionId: number): void }>()

const { t } = useI18n()
const { options: dictOptions } = useDict()

const forms = ref<OaForm[]>([])
const flowDefs = ref<OaFlowDefOption[]>([])
const categoryOptions = ref<{ value: string; label: string }[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const [f, d] = await Promise.all([listOaForms(), listOaFlowDefs()])
    forms.value = f
    flowDefs.value = d
  } catch {
    forms.value = []
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  void load()
  try {
    categoryOptions.value = await dictOptions('oa_category')
  } catch {
    categoryOptions.value = []
  }
})

const flowNameOf = computed(() => {
  const m = new Map(flowDefs.value.map((d) => [d.id, d.name]))
  return (id: number | null) => (id ? (m.get(id) ?? `#${id}`) : '')
})

const columns: ListColumn[] = [
  { prop: 'name', labelKey: 'oa.design.formName', minWidth: 140, fixed: 'left' },
  { prop: 'key', labelKey: 'oa.design.formKey', width: 150 },
  { prop: 'category', labelKey: 'oa.design.category', width: 90 },
  { prop: 'formVersion', labelKey: 'oa.design.version', width: 70 },
  { prop: 'status', labelKey: 'oa.my.status', width: 96 },
  { prop: 'flowDefinitionId', labelKey: 'oa.design.boundFlow', minWidth: 140 },
  { prop: 'publishedAt', labelKey: 'oa.design.publishedAt', width: 165 },
]

function categoryLabel(c: string) {
  return categoryOptions.value.find((o) => o.value === c)?.label || c || '-'
}

/* ---------- 新建/编辑弹窗 ---------- */
const FIELD_TYPES: OaFieldType[] = [
  'text', 'textarea', 'number', 'money', 'date', 'daterange', 'select', 'radio', 'checkbox', 'file', 'user',
]
const OPTION_TYPES: OaFieldType[] = ['select', 'radio', 'checkbox']

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)
const selectedFieldIdx = ref(0)
const previewData = ref<Record<string, unknown>>({})

const form = reactive({
  key: '',
  name: '',
  category: 'other',
  icon: 'Document',
  sort: 0,
  description: '',
  flowDefinitionId: null as number | null,
  fields: [] as OaField[],
})

const selectedField = computed(() => form.fields[selectedFieldIdx.value] ?? null)

/** 选项 textarea 与 string[] 互转 */
const optionsText = computed({
  get: () => (selectedField.value?.options ?? []).join('\n'),
  set: (v: string) => {
    if (selectedField.value) {
      selectedField.value.options = v.split('\n').map((s) => s.trim()).filter(Boolean)
    }
  },
})

function blankField(idx: number): OaField {
  return { key: `field_${idx}`, label: '', type: 'text', required: false }
}

function addField() {
  form.fields.push(blankField(form.fields.length + 1))
  selectedFieldIdx.value = form.fields.length - 1
}

function removeField(idx: number) {
  form.fields.splice(idx, 1)
  if (selectedFieldIdx.value >= form.fields.length) selectedFieldIdx.value = Math.max(0, form.fields.length - 1)
}

function moveField(idx: number, dir: -1 | 1) {
  const target = idx + dir
  if (target < 0 || target >= form.fields.length) return
  const a = form.fields[idx]!
  form.fields[idx] = form.fields[target]!
  form.fields[target] = a
  selectedFieldIdx.value = target
}

function onFieldTypeChange(f: OaField) {
  // 切换为选项类控件时补默认选项（占位值，用户在选项框中改写）
  if (OPTION_TYPES.includes(f.type) && !f.options?.length) f.options = ['A', 'B']
}

function openCreate() {
  editingId.value = null
  Object.assign(form, {
    key: '', name: '', category: 'other', icon: 'Document', sort: 0, description: '',
    flowDefinitionId: null, fields: [blankField(1)],
  })
  selectedFieldIdx.value = 0
  previewData.value = {}
  dialogVisible.value = true
}

function openEdit(row: OaForm) {
  editingId.value = row.id
  Object.assign(form, {
    key: row.key,
    name: row.name,
    category: row.category,
    icon: row.icon || 'Document',
    sort: row.sort,
    description: row.description,
    flowDefinitionId: row.flowDefinitionId,
    fields: (row.fields ?? []).map((f) => ({ ...f, options: f.options ? [...f.options] : undefined })),
  })
  selectedFieldIdx.value = 0
  previewData.value = {}
  dialogVisible.value = true
}

function validateForm(): string | null {
  if (!/^[a-z][a-z0-9_]*$/.test(form.key)) return t('oa.design.formKeyTip')
  if (!form.name.trim()) return t('oa.design.formName')
  if (!form.fields.length) return t('oa.design.fields')
  const keys = new Set<string>()
  for (const f of form.fields) {
    if (!/^[a-z][a-z0-9_]*$/.test(f.key) || keys.has(f.key)) return `${t('oa.design.fieldKey')}: ${f.key}`
    keys.add(f.key)
    if (!f.label.trim()) return `${t('oa.design.fieldLabel')}: ${f.key}`
    if (OPTION_TYPES.includes(f.type) && !f.options?.length) return `${t('oa.design.options')}: ${f.key}`
  }
  return null
}

async function save() {
  const err = validateForm()
  if (err) {
    ElMessage.warning(err)
    return
  }
  const payload: OaFormPayload = {
    key: form.key,
    name: form.name,
    category: form.category,
    icon: form.icon,
    sort: form.sort,
    description: form.description,
    flowDefinitionId: form.flowDefinitionId,
    fields: form.fields.map((f) => ({
      key: f.key,
      label: f.label,
      type: f.type,
      required: Boolean(f.required),
      options: OPTION_TYPES.includes(f.type) ? f.options : undefined,
      placeholder: f.placeholder || undefined,
      maxlength: f.maxlength || undefined,
      exposeVariable: Boolean(f.exposeVariable),
    })),
  }
  saving.value = true
  try {
    if (editingId.value) await updateOaForm(editingId.value, payload)
    else await createOaForm(payload)
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    void load()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

/* ---------- 发布 / 停用 / 版本 / 删除 ---------- */
async function doPublish(row: OaForm) {
  try {
    await ElMessageBox.confirm(t('oa.design.publishConfirm'), t('oa.design.publish'), { type: 'warning' })
    await publishOaForm(row.id)
    ElMessage.success(t('oa.design.publishDone'))
    void load()
  } catch {
    /* cancel or http notifies */
  }
}

async function doDisable(row: OaForm) {
  try {
    await ElMessageBox.confirm(t('oa.design.disableConfirm'), t('oa.design.disable'), { type: 'warning' })
    await disableOaForm(row.id)
    ElMessage.success(t('oa.design.disableDone'))
    void load()
  } catch {
    /* cancel or http notifies */
  }
}

async function doNewVersion(row: OaForm) {
  try {
    await ElMessageBox.confirm(t('oa.design.newVersionConfirm'), t('oa.design.newVersion'), { type: 'info' })
    await newOaFormVersion(row.id)
    ElMessage.success(t('oa.design.newVersionDone'))
    void load()
  } catch {
    /* cancel or http notifies */
  }
}

async function doDelete(row: OaForm) {
  try {
    await ElMessageBox.confirm(t('oa.design.deleteConfirm'), t('common.action.delete'), { type: 'warning' })
    await deleteOaForm(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    void load()
  } catch {
    /* cancel or http notifies */
  }
}

const editable = (row: OaForm) => row.status === 'draft' || row.status === 'disabled'

function gotoDesign() {
  if (form.flowDefinitionId) emit('goto-def', form.flowDefinitionId)
}
</script>

<template>
  <div class="oa-form-panel">
    <div class="panel-toolbar">
      <el-button v-permission="'oa:admin:design'" type="primary" @click="openCreate">
        {{ t('oa.design.createForm') }}
      </el-button>
      <el-button @click="load">{{ t('common.action.refresh') }}</el-button>
    </div>

    <ListTable :columns="columns" :data="forms as unknown as Record<string, unknown>[]" :loading="loading" :total="forms.length" :page="1" :size="Math.max(forms.length, 10)" row-key="id">
      <template #category="{ row }">{{ categoryLabel(String(row.category)) }}</template>
      <template #status="{ row }">
        <StatusTag :status="String(row.status)" i18n-prefix="oa.formStatus" />
      </template>
      <template #flowDefinitionId="{ row }">
        <span v-if="row.flowDefinitionId">{{ flowNameOf(Number(row.flowDefinitionId)) }}</span>
        <span v-else class="muted">{{ t('oa.design.noFlow') }}</span>
      </template>
      <template #publishedAt="{ row }">{{ row.publishedAt || '-' }}</template>
      <template #extraColumns>
        <el-table-column :label="t('common.action.operate')" width="280" fixed="right">
          <template #default="{ row }">
            <el-button v-if="editable(row as OaForm)" v-permission="'oa:admin:design'" link type="primary" @click="openEdit(row as OaForm)">
              {{ t('common.action.edit') }}
            </el-button>
            <el-button v-if="row.status !== 'published'" v-permission="'oa:admin:design'" link type="success" @click="doPublish(row as OaForm)">
              {{ t('oa.design.publish') }}
            </el-button>
            <el-button v-if="row.status === 'published'" v-permission="'oa:admin:design'" link type="warning" @click="doDisable(row as OaForm)">
              {{ t('oa.design.disable') }}
            </el-button>
            <el-button v-if="row.status === 'published'" v-permission="'oa:admin:design'" link type="primary" @click="doNewVersion(row as OaForm)">
              {{ t('oa.design.newVersion') }}
            </el-button>
            <el-button v-if="row.status === 'draft'" v-permission="'oa:admin:design'" link type="danger" @click="doDelete(row as OaForm)">
              {{ t('common.action.delete') }}
            </el-button>
          </template>
        </el-table-column>
      </template>
    </ListTable>

    <el-dialog v-model="dialogVisible" :title="editingId ? t('oa.design.editForm') : t('oa.design.createForm')" width="1080px" append-to-body>
      <div class="form-designer">
        <div class="fd-left">
          <el-form label-width="96px" size="default">
            <el-form-item :label="t('oa.design.formKey')">
              <el-input v-model="form.key" :disabled="Boolean(editingId)" :placeholder="t('oa.design.formKeyTip')" />
            </el-form-item>
            <el-form-item :label="t('oa.design.formName')">
              <el-input v-model="form.name" />
            </el-form-item>
            <el-form-item :label="t('oa.design.category')">
              <el-select v-model="form.category" style="width: 100%">
                <el-option v-for="o in categoryOptions" :key="o.value" :value="o.value" :label="o.label" />
              </el-select>
            </el-form-item>
            <el-form-item :label="t('oa.design.icon')">
              <el-input v-model="form.icon" :placeholder="t('oa.design.iconTip')" />
            </el-form-item>
            <el-form-item :label="t('oa.design.sort')">
              <el-input-number v-model="form.sort" :min="0" :max="999" />
            </el-form-item>
            <el-form-item :label="t('oa.design.description')">
              <el-input v-model="form.description" type="textarea" :rows="2" />
            </el-form-item>
            <el-form-item :label="t('oa.design.boundFlow')">
              <div class="flow-bind">
                <el-select v-model="form.flowDefinitionId" clearable :placeholder="t('oa.design.noFlow')" style="flex: 1">
                  <el-option v-for="d in flowDefs" :key="d.id" :value="d.id" :label="`${d.name} (${d.code})`" />
                </el-select>
                <el-button :disabled="!form.flowDefinitionId" @click="gotoDesign">{{ t('oa.design.goDesign') }}</el-button>
              </div>
            </el-form-item>
          </el-form>

          <div class="section-title">{{ t('oa.design.fields') }}</div>
          <div class="field-list">
            <div
              v-for="(f, idx) in form.fields"
              :key="idx"
              class="field-item"
              :class="{ active: idx === selectedFieldIdx }"
              @click="selectedFieldIdx = idx"
            >
              <span class="field-item-label">{{ f.label || f.key || `#${idx + 1}` }}</span>
              <el-tag size="small" effect="plain">{{ t(`oa.fieldType.${f.type}`) }}</el-tag>
              <span class="field-item-ops" @click.stop>
                <el-button link size="small" @click="moveField(idx, -1)">↑</el-button>
                <el-button link size="small" @click="moveField(idx, 1)">↓</el-button>
                <el-button link size="small" type="danger" @click="removeField(idx)">×</el-button>
              </span>
            </div>
            <el-button plain type="primary" size="small" @click="addField">{{ t('oa.design.addField') }}</el-button>
          </div>

          <template v-if="selectedField">
            <el-form label-width="96px" size="small" class="field-props">
              <el-form-item :label="t('oa.design.fieldKey')">
                <el-input v-model="selectedField.key" placeholder="leave_type" />
              </el-form-item>
              <el-form-item :label="t('oa.design.fieldLabel')">
                <el-input v-model="selectedField.label" />
              </el-form-item>
              <el-form-item :label="t('oa.design.fieldType')">
                <el-select v-model="selectedField.type" style="width: 100%" @change="onFieldTypeChange(selectedField)">
                  <el-option v-for="ft in FIELD_TYPES" :key="ft" :value="ft" :label="t(`oa.fieldType.${ft}`)" />
                </el-select>
              </el-form-item>
              <el-form-item :label="t('oa.design.required')">
                <el-switch v-model="selectedField.required" />
              </el-form-item>
              <el-form-item v-if="OPTION_TYPES.includes(selectedField.type)" :label="t('oa.design.options')">
                <el-input v-model="optionsText" type="textarea" :rows="3" :placeholder="t('oa.design.optionsTip')" />
              </el-form-item>
              <el-form-item :label="t('oa.design.placeholder')">
                <el-input v-model="selectedField.placeholder" />
              </el-form-item>
              <el-form-item v-if="selectedField.type === 'text' || selectedField.type === 'textarea'" :label="t('oa.design.maxlength')">
                <el-input-number v-model="selectedField.maxlength" :min="0" :max="5000" />
              </el-form-item>
              <el-form-item :label="t('oa.design.exposeVariable')">
                <el-switch v-model="selectedField.exposeVariable" />
                <div class="prop-tip">{{ t('oa.design.exposeTip') }}</div>
              </el-form-item>
            </el-form>
          </template>
        </div>

        <div class="fd-right">
          <div class="section-title">{{ t('oa.design.preview') }}</div>
          <div class="preview-box">
            <FormRenderer :fields="form.fields" v-model="previewData" />
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.oa-form-panel {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  height: 100%;
  min-height: 0;
}

.panel-toolbar {
  display: flex;
  gap: var(--bs-space-2);
  flex-shrink: 0;
}

.form-designer {
  display: flex;
  gap: var(--bs-space-3);
}

.fd-left {
  flex: 1.2;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.fd-right {
  flex: 1;
  min-width: 0;
  border-left: 1px solid var(--bs-color-border-subtle);
  padding-left: var(--bs-space-3);
}

.section-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.field-list {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-1);
}

.field-item {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  padding: 4px var(--bs-space-2);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-sm);
  cursor: pointer;
}

.field-item.active {
  border-color: var(--bs-color-primary);
  background: var(--bs-color-fill-light);
}

.field-item-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.field-props {
  margin-top: var(--bs-space-2);
}

.prop-tip {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  line-height: 1.4;
}

.flow-bind {
  display: flex;
  gap: var(--bs-space-2);
  width: 100%;
}

.preview-box {
  background: var(--bs-color-fill-lighter);
  border-radius: var(--bs-radius-md);
  padding: var(--bs-space-3);
}

.muted {
  color: var(--bs-color-fg-muted);
}
</style>
