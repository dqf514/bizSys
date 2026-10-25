<script setup lang="ts">
/** OA 表单设计（统一流程设计页的第二页签）：表单列表 + 全屏新建/编辑（顶部基础设置与保存/取消 + 三栏字段设计器）。
 * 字段设计器复刻 TPCworkflow FormDesigner 交互（字段面板/画布实时预览/属性编辑），数据模型保持 fields[]。
 * 设计过程防抖自动保存本地草稿（localStorage，按 userId+formKey 隔离），意外关闭后可恢复；仅防意外，
 * 不改变后端草稿/发布语义。绑定流程下拉右侧"去设计" → emit('goto-def', flowDefinitionId)。
 */
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import FormDesigner from '@/modules/oa/components/FormDesigner.vue'
import { useDict } from '@/composables/useDict'
import {
  clearOaFormDesignDraft,
  oaFormDesignDraftKey,
  readOaFormDesignDraft,
  writeOaFormDesignDraft,
  type OaFormDesignDraftMeta,
} from '@/composables/oaFormDesignDraft'
import { useAuthStore } from '@/stores/auth'
import {
  bindLatestFlow,
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
const auth = useAuthStore()

const forms = ref<OaForm[]>([])
const flowDefs = ref<OaFlowDefOption[]>([])
const categoryOptions = ref<{ value: string; label: string }[]>([])
const loading = ref(false)
/** 本地全量列表：前端关键词过滤（name/key） */
const formKeyword = ref('')
const filteredForms = computed(() => {
  const kw = formKeyword.value.trim().toLowerCase()
  if (!kw) return forms.value
  return forms.value.filter(
    (f) => f.name?.toLowerCase().includes(kw) || f.key?.toLowerCase().includes(kw),
  )
})

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
  { prop: 'name', labelKey: 'oa.design.formName', minWidth: 140, fixed: 'left', sortable: 'local' },
  { prop: 'key', labelKey: 'oa.design.formKey', width: 150, sortable: 'local' },
  { prop: 'category', labelKey: 'oa.design.category', width: 90, sortable: 'local' },
  { prop: 'formVersion', labelKey: 'oa.design.version', width: 70, sortable: 'local' },
  { prop: 'status', labelKey: 'oa.my.status', width: 96, sortable: 'local' },
  { prop: 'flowDefinitionId', labelKey: 'oa.design.boundFlow', minWidth: 140 },
  { prop: 'publishedAt', labelKey: 'oa.design.publishedAt', width: 165, sortable: 'local' },
]

function categoryLabel(c: string) {
  return categoryOptions.value.find((o) => o.value === c)?.label || c || '-'
}

/* ---------- 新建/编辑（全屏设计器） ---------- */
const OPTION_TYPES: OaFieldType[] = ['select', 'radio', 'checkbox']

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const saving = ref(false)

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

/* ---------- 设计器本地草稿（防抖自动保存） ---------- */
const DRAFT_DEBOUNCE_MS = 1800
const savedAt = ref('')
let saveTimer: ReturnType<typeof setTimeout> | null = null

// 编辑态以 formKey 隔离（编辑时 key 锁定不变）；新建固定用 "new"
const draftKey = computed(() =>
  oaFormDesignDraftKey(auth.user?.id, editingId.value ? form.key : 'new'),
)

function hhmmss(d: Date) {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

function snapshotMeta(): OaFormDesignDraftMeta {
  return {
    key: form.key,
    name: form.name,
    category: form.category,
    icon: form.icon,
    sort: form.sort,
    description: form.description,
    flowDefinitionId: form.flowDefinitionId,
  }
}

function persistDraft() {
  saveTimer = null
  if (!dialogVisible.value) return
  if (writeOaFormDesignDraft(draftKey.value, { meta: snapshotMeta(), fields: form.fields, savedAt: Date.now() })) {
    savedAt.value = hhmmss(new Date())
  }
}

watch(
  form,
  () => {
    if (!dialogVisible.value) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(persistDraft, DRAFT_DEBOUNCE_MS)
  },
  { deep: true },
)

function onBeforeUnload(e: BeforeUnloadEvent) {
  if (dialogVisible.value && readOaFormDesignDraft(draftKey.value)) e.preventDefault()
}
window.addEventListener('beforeunload', onBeforeUnload)

onBeforeUnmount(() => {
  window.removeEventListener('beforeunload', onBeforeUnload)
  if (saveTimer) {
    clearTimeout(saveTimer)
    persistDraft() /* 组件卸载前把最后一次防抖内的修改落盘 */
  }
})

/** 打开前检测本地草稿：恢复 / 丢弃 / 关闭提示（保留草稿但不恢复，下次仍会提示） */
async function promptDraftIfAny(key: string): Promise<'restored' | 'fresh'> {
  const draft = readOaFormDesignDraft(key)
  if (!draft) return 'fresh'
  try {
    await ElMessageBox.confirm(
      t('oa.design.draftFound', { time: new Date(draft.savedAt).toLocaleString() }),
      t('oa.design.draftRestoreTitle'),
      {
        type: 'warning',
        confirmButtonText: t('oa.design.draftRestore'),
        cancelButtonText: t('oa.design.draftDiscard'),
        distinguishCancelAndClose: true,
      },
    )
    Object.assign(form, draft.meta, { fields: draft.fields })
    savedAt.value = hhmmss(new Date(draft.savedAt))
    return 'restored'
  } catch (action) {
    if (action === 'cancel') clearOaFormDesignDraft(key) /* 明确丢弃 */
    return 'fresh' /* close：保留草稿，按非草稿内容继续 */
  }
}

async function openCreate() {
  editingId.value = null
  savedAt.value = ''
  Object.assign(form, {
    key: '', name: '', category: 'other', icon: 'Document', sort: 0, description: '',
    flowDefinitionId: null, fields: [],
  })
  await promptDraftIfAny(oaFormDesignDraftKey(auth.user?.id, 'new'))
  dialogVisible.value = true
}

async function openEdit(row: OaForm) {
  editingId.value = row.id
  savedAt.value = ''
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
  await promptDraftIfAny(oaFormDesignDraftKey(auth.user?.id, row.key))
  dialogVisible.value = true
}

/** 关闭前确认：有草稿时选择丢弃（确认）/保留（取消）/继续编辑（叉掉提示）；返回是否关闭 */
async function confirmDiscard(): Promise<'close' | 'stay'> {
  if (saveTimer) {
    clearTimeout(saveTimer)
    persistDraft()
  }
  if (!readOaFormDesignDraft(draftKey.value)) return 'close'
  try {
    await ElMessageBox.confirm(t('oa.design.cancelTip'), t('common.action.cancel'), {
      type: 'warning',
      confirmButtonText: t('oa.design.discardDraft'),
      cancelButtonText: t('oa.design.keepDraft'),
      distinguishCancelAndClose: true,
    })
    clearOaFormDesignDraft(draftKey.value) /* 确认 = 丢弃草稿并关闭 */
    savedAt.value = ''
    return 'close'
  } catch (action) {
    return action === 'cancel' ? 'close' : 'stay' /* cancel=保留草稿关闭；close=回到编辑 */
  }
}

/** 取消按钮 / X / ESC 统一走同一确认流 */
async function onCancelClick() {
  if ((await confirmDiscard()) === 'close') dialogVisible.value = false
}

async function beforeClose(done: () => void) {
  if ((await confirmDiscard()) === 'close') done()
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
    // 手工选项且未配级联时才强制要求选项；字典源需 dictType
    if (
      OPTION_TYPES.includes(f.type) &&
      (f.optionsSource ?? 'manual') === 'manual' &&
      !f.options?.length &&
      !f.cascade
    ) {
      return `${t('oa.design.options')}: ${f.key}`
    }
    if (OPTION_TYPES.includes(f.type) && f.optionsSource === 'dict' && !f.dictType?.trim()) {
      return `${t('oa.design.dictType')}: ${f.key}`
    }
    if (f.type === 'resource' && !f.resource) return `${t('oa.design.resourceType')}: ${f.key}`
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
      span: f.span ?? undefined,
      description: f.description || undefined,
      defaultValue: f.defaultValue ?? undefined,
      showWhen: f.showWhen ?? undefined,
      requiredWhen: f.requiredWhen ?? undefined,
      readonlyWhen: f.readonlyWhen ?? undefined,
      optionsSource: OPTION_TYPES.includes(f.type) ? (f.optionsSource ?? 'manual') : undefined,
      dictType: f.dictType || undefined,
      cascade: f.cascade ?? undefined,
      resource: f.type === 'resource' ? f.resource || undefined : undefined,
      mappings: f.type === 'resource' && f.mappings?.length ? f.mappings : undefined,
    })),
  }
  saving.value = true
  try {
    if (editingId.value) await updateOaForm(editingId.value, payload)
    else await createOaForm(payload)
    if (saveTimer) clearTimeout(saveTimer)
    clearOaFormDesignDraft(draftKey.value) /* 正式保存成功后清除本地草稿 */
    savedAt.value = ''
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

const DESIGN_PERM = 'oa:admin:design'

function rowActions(row: OaForm): ActionItem[] {
  const acts: ActionItem[] = []
  if (editable(row)) acts.push({ key: 'edit', tip: 'common.action.edit', perm: DESIGN_PERM })
  if (row.status !== 'published') {
    acts.push({ key: 'publish', tip: 'oa.design.publish', icon: 'Promotion', perm: DESIGN_PERM })
  }
  if (row.status === 'published') {
    acts.push({ key: 'disable', tip: 'oa.design.disable', perm: DESIGN_PERM })
    acts.push({ key: 'newVersion', tip: 'oa.design.newVersion', icon: 'DocumentCopy', perm: DESIGN_PERM })
  }
  if (flowStale(row)) acts.push({ key: 'bindLatest', tip: 'oa.design.bindLatest', icon: 'Link', perm: DESIGN_PERM })
  if (row.status === 'draft') acts.push({ key: 'delete', tip: 'common.action.delete', perm: DESIGN_PERM })
  return acts
}

function onAction(key: string, row: OaForm) {
  if (key === 'edit') void openEdit(row)
  else if (key === 'publish') void doPublish(row)
  else if (key === 'disable') void doDisable(row)
  else if (key === 'newVersion') void doNewVersion(row)
  else if (key === 'bindLatest') void doBindLatest(row)
  else if (key === 'delete') void doDelete(row)
}

/** 绑定流程落后最新启用版本（可一键绑定最新版） */
const flowStale = (row: OaForm) =>
  Boolean(row.flowDefinitionId && row.flowVersion != null && row.flowLatestVersion != null
    && row.flowLatestVersion > row.flowVersion)

async function doBindLatest(row: OaForm) {
  try {
    await ElMessageBox.confirm(
      t('oa.design.bindLatestConfirm', { version: row.flowLatestVersion }),
      t('oa.design.bindLatest'),
      { type: 'info' },
    )
    await bindLatestFlow(row.id)
    ElMessage.success(t('oa.design.bindLatestDone', { version: row.flowLatestVersion }))
    void load()
  } catch {
    /* cancel or http notifies */
  }
}

function gotoDesign() {
  if (form.flowDefinitionId) emit('goto-def', form.flowDefinitionId)
}
</script>

<template>
  <div class="oa-form-panel">
    <div class="panel-toolbar">
      <el-input
        v-model="formKeyword"
        :placeholder="t('common.form.placeholderSearch')"
        :prefix-icon="Search"
        clearable
        class="local-filter"
      />
      <el-button v-permission="'oa:admin:design'" type="primary" @click="openCreate">
        {{ t('oa.design.createForm') }}
      </el-button>
      <el-button @click="load">{{ t('common.action.refresh') }}</el-button>
    </div>

    <ListTable :columns="columns" :data="filteredForms as unknown as Record<string, unknown>[]" :loading="loading" :total="filteredForms.length" :page="1" :size="Math.max(filteredForms.length, 10)" row-key="id">
      <template #category="{ row }">{{ categoryLabel(String(row.category)) }}</template>
      <template #status="{ row }">
        <StatusTag :status="String(row.status)" i18n-prefix="oa.formStatus" />
      </template>
      <template #flowDefinitionId="{ row }">
        <template v-if="row.flowDefinitionId">
          <span>{{ row.flowName || flowNameOf(Number(row.flowDefinitionId)) }} v{{ row.flowVersion ?? 1 }}</span>
          <el-tag v-if="flowStale(row as OaForm)" type="warning" size="small" effect="plain" class="stale-tag">
            {{ t('oa.design.flowStale', { version: row.flowLatestVersion }) }}
          </el-tag>
        </template>
        <span v-else class="muted">{{ t('oa.design.noFlow') }}</span>
      </template>
      <template #publishedAt="{ row }">{{ row.publishedAt || '-' }}</template>
      <template #extraColumns>
        <el-table-column :label="t('common.action.operate')" width="130" fixed="right" align="center" header-align="center">
          <template #default="{ row }">
            <ActionBar :actions="rowActions(row as OaForm)" @select="(key: string) => onAction(key, row as OaForm)" />
          </template>
        </el-table-column>
      </template>
    </ListTable>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? t('oa.design.editForm') : t('oa.design.createForm')"
      fullscreen
      append-to-body
      class="oa-form-designer-dialog"
      :before-close="beforeClose"
    >
      <div class="designer-shell">
        <div class="designer-topbar">
          <el-form class="topbar-form" label-width="92px" size="default">
            <el-row :gutter="12">
              <el-col :span="4">
                <el-form-item :label="t('oa.design.formKey')">
                  <el-input v-model="form.key" :disabled="Boolean(editingId)" :placeholder="t('oa.design.formKeyTip')" />
                </el-form-item>
              </el-col>
              <el-col :span="6">
                <el-form-item :label="t('oa.design.formName')">
                  <el-input v-model="form.name" />
                </el-form-item>
              </el-col>
              <el-col :span="5">
                <el-form-item :label="t('oa.design.category')">
                  <el-select v-model="form.category" style="width: 100%">
                    <el-option v-for="o in categoryOptions" :key="o.value" :value="o.value" :label="o.label" />
                  </el-select>
                </el-form-item>
              </el-col>
              <el-col :span="5">
                <el-form-item :label="t('oa.design.icon')">
                  <el-input v-model="form.icon" :placeholder="t('oa.design.iconTip')" />
                </el-form-item>
              </el-col>
              <el-col :span="4">
                <el-form-item :label="t('oa.design.sort')">
                  <el-input-number v-model="form.sort" :min="0" :max="999" style="width: 100%" />
                </el-form-item>
              </el-col>
            </el-row>
            <el-row :gutter="12">
              <el-col :span="10">
                <el-form-item :label="t('oa.design.boundFlow')">
                  <div class="flow-bind">
                    <el-select v-model="form.flowDefinitionId" clearable :placeholder="t('oa.design.noFlow')" style="flex: 1">
                      <el-option v-for="d in flowDefs" :key="d.id" :value="d.id" :label="`${d.name} (${d.code})`" />
                    </el-select>
                    <el-button :disabled="!form.flowDefinitionId" @click="gotoDesign">{{ t('oa.design.goDesign') }}</el-button>
                  </div>
                </el-form-item>
              </el-col>
              <el-col :span="14">
                <el-form-item :label="t('oa.design.description')">
                  <el-input v-model="form.description" type="textarea" :rows="1" />
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>
          <div class="topbar-side">
            <span v-if="savedAt" class="saved-at">{{ t('oa.form.autoSaved', { time: savedAt }) }}</span>
            <div class="topbar-actions">
              <el-button @click="onCancelClick">{{ t('common.action.cancel') }}</el-button>
              <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
            </div>
          </div>
        </div>

        <FormDesigner v-model:fields="form.fields" class="designer-main" />
      </div>
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

.local-filter {
  width: 220px;
}

.designer-shell {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

/* 顶部基础设置 + 操作（常驻不滚动） */
.designer-topbar {
  display: flex;
  gap: var(--bs-space-3);
  flex-shrink: 0;
  border-bottom: 1px solid var(--bs-color-border-subtle);
  padding-bottom: var(--bs-space-2);
  margin-bottom: var(--bs-space-3);
}

.topbar-form {
  flex: 1;
  min-width: 0;
}

.topbar-form :deep(.el-form-item) {
  margin-bottom: var(--bs-space-2);
}

.topbar-side {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--bs-space-1);
  padding-bottom: var(--bs-space-2);
}

.topbar-actions {
  display: flex;
  gap: var(--bs-space-2);
}

.topbar-actions .el-button + .el-button {
  margin-left: 0;
}

.saved-at {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
  white-space: nowrap;
}

.designer-main {
  flex: 1;
  min-height: 0;
}

.flow-bind {
  display: flex;
  gap: var(--bs-space-2);
  width: 100%;
}

.muted {
  color: var(--bs-color-fg-muted);
}

.stale-tag {
  margin-left: var(--bs-space-1);
}
</style>

<!-- 全屏弹窗 body 布局（teleport 到 body，scoped 不可达，用全局类） -->
<style>
.oa-form-designer-dialog.is-fullscreen {
  display: flex;
  flex-direction: column;
}

.oa-form-designer-dialog .el-dialog__body {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  padding: var(--bs-space-3) var(--bs-space-4);
}
</style>
