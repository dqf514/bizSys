<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import PageHeader from '@/components/common/PageHeader.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import {
  createTool,
  createToolLoan,
  deleteTool,
  deleteToolLoan,
  getTool,
  listTools,
  returnToolLoan,
  toolCounts,
  updateTool,
  updateToolLoan,
} from '@/api/asset'
import type { AssetTool, AssetToolLoan } from '@/api/types'
import { useDeptTree, useWarehouseOptions } from '../composables/useAssetOptions'
import { useDictOptions } from '@/composables/useDict'

defineOptions({ name: 'ToolList' })

const { t } = useI18n()
const deptTree = useDeptTree()
const warehouseOpts = useWarehouseOptions()
const categoryDict = useDictOptions('asset_category')

const counts = ref<Record<string, number>>({})
const tools = ref<AssetTool[]>([])
const keyword = ref('')
const statusFilter = ref('')
const loading = ref(false)
const currentId = ref<number | null>(null)
const loans = ref<AssetToolLoan[]>([])
const loanLoading = ref(false)

const STATUS_OPTIONS = ['in_stock', 'loaned', 'maintenance', 'scrapped'] as const

const statCards = computed(() => [
  { key: 'statTotal', label: t('asset.tool.statTotal'), value: counts.value.all ?? 0 },
  { key: 'statInStock', label: t('asset.tool.statInStock'), value: counts.value.in_stock ?? 0 },
  { key: 'statLoaned', label: t('asset.tool.statLoaned'), value: counts.value.loaned ?? 0 },
  { key: 'statMaintenance', label: t('asset.tool.statMaintenance'), value: counts.value.maintenance ?? 0 },
])

function fmtNumber(v: unknown) {
  const n = Number(v ?? 0)
  return Number.isFinite(n) ? n.toLocaleString() : '0'
}

async function loadCounts() {
  try {
    counts.value = (await toolCounts()) ?? {}
  } catch {
    counts.value = {}
  }
}

async function loadTools() {
  loading.value = true
  try {
    const data = await listTools({
      page: 1,
      size: 200,
      q: keyword.value || undefined,
      filters: { status: statusFilter.value || undefined },
    })
    tools.value = data.items ?? []
    if (!tools.value.length) {
      currentId.value = null
      loans.value = []
      return
    }
    const stillThere = tools.value.some((x) => x.id === currentId.value)
    const first = tools.value[0]
    if (!stillThere && first) await selectTool(first.id)
  } catch {
    tools.value = []
  } finally {
    loading.value = false
  }
}

async function selectTool(id: number) {
  currentId.value = id
  loanLoading.value = true
  try {
    const data = await getTool(id)
    loans.value = data.loans ?? []
  } catch {
    loans.value = []
  } finally {
    loanLoading.value = false
  }
}

async function refreshAll() {
  await Promise.all([loadCounts(), loadTools()])
}

onMounted(() => void refreshAll())

function onSearch() {
  void loadTools()
}

function resetSearch() {
  keyword.value = ''
  statusFilter.value = ''
  void loadTools()
}

/* ---------- tool actions ---------- */
function toolActions(_row: AssetTool): ActionItem[] {
  return [
    { key: 'edit', tip: 'common.action.edit', perm: 'asset:tool:edit' },
    { key: 'delete', tip: 'common.action.delete', perm: 'asset:tool:delete' },
  ]
}

function onToolAction(key: string, row: AssetTool) {
  if (key === 'edit') openToolEdit(row)
  else if (key === 'delete') void removeTool(row)
}

const toolDialogVisible = ref(false)
const toolDialogTitle = ref('')
const toolFormRef = ref<FormInstance>()
const toolSaving = ref(false)
const toolEditingId = ref<number | null>(null)
const toolForm = reactive({
  toolNo: '',
  name: '',
  spec: '',
  model: '',
  category: '',
  unit: '',
  warehouseId: null as number | null,
  deptId: null as number | null,
  purchaseDate: '',
  value: null as number | null,
  remark: '',
  status: 'in_stock',
  version: null as number | null,
})

function openToolCreate() {
  toolEditingId.value = null
  toolDialogTitle.value = t('asset.tool.create')
  Object.assign(toolForm, {
    toolNo: '',
    name: '',
    spec: '',
    model: '',
    category: '',
    unit: '',
    warehouseId: null,
    deptId: null,
    purchaseDate: '',
    value: null,
    remark: '',
    status: 'in_stock',
    version: null,
  })
  toolDialogVisible.value = true
}

function openToolEdit(row: AssetTool) {
  toolEditingId.value = row.id
  toolDialogTitle.value = t('asset.tool.edit')
  Object.assign(toolForm, {
    toolNo: row.toolNo,
    name: row.name,
    spec: row.spec,
    model: row.model,
    category: row.category,
    unit: row.unit,
    warehouseId: row.warehouseId ?? null,
    deptId: row.deptId ?? null,
    purchaseDate: row.purchaseDate ?? '',
    value: row.value ?? null,
    remark: row.remark,
    status: row.status,
    version: row.version,
  })
  toolDialogVisible.value = true
}

async function saveTool() {
  if (!toolFormRef.value) return
  const ok = await toolFormRef.value.validate().catch(() => false)
  if (!ok) return
  toolSaving.value = true
  try {
    if (toolEditingId.value) await updateTool(toolEditingId.value, { ...toolForm })
    else await createTool({ ...toolForm })
    ElMessage.success(t('common.message.saveSuccess'))
    toolDialogVisible.value = false
    await refreshAll()
  } catch {
    /* http notifies */
  } finally {
    toolSaving.value = false
  }
}

async function removeTool(row: AssetTool) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteTool(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    if (currentId.value === row.id) currentId.value = null
    await refreshAll()
  } catch {
    /* http notifies */
  }
}

/* ---------- loan actions ---------- */
function loanActions(row: AssetToolLoan): ActionItem[] {
  const acts: ActionItem[] = []
  if (row.status === 'borrowed') {
    acts.push({ key: 'edit', tip: 'common.action.edit', perm: 'asset:toolLoan:edit' })
    acts.push({ key: 'return', tip: 'asset.tool.return', icon: 'RefreshLeft', perm: 'asset:toolLoan:return' })
    acts.push({ key: 'delete', tip: 'common.action.delete', perm: 'asset:toolLoan:delete' })
  }
  return acts
}

function onLoanAction(key: string, row: AssetToolLoan) {
  if (key === 'edit') openLoanEdit(row)
  else if (key === 'return') void doReturn(row)
  else if (key === 'delete') void removeLoan(row)
}

const loanDialogVisible = ref(false)
const loanDialogTitle = ref('')
const loanFormRef = ref<FormInstance>()
const loanSaving = ref(false)
const loanEditingId = ref<number | null>(null)
const loanForm = reactive({
  toolId: null as number | null,
  borrowerName: '',
  deptId: null as number | null,
  loanDate: '',
  dueDate: '',
  purpose: '',
  remark: '',
  version: null as number | null,
})

function openLoanCreate() {
  if (!currentId.value) return
  loanEditingId.value = null
  loanDialogTitle.value = t('asset.tool.createLoan')
  Object.assign(loanForm, {
    toolId: currentId.value,
    borrowerName: '',
    deptId: null,
    loanDate: '',
    dueDate: '',
    purpose: '',
    remark: '',
    version: null,
  })
  loanDialogVisible.value = true
}

function openLoanEdit(row: AssetToolLoan) {
  loanEditingId.value = row.id
  loanDialogTitle.value = t('asset.tool.editLoan')
  Object.assign(loanForm, {
    toolId: row.toolId,
    borrowerName: row.borrowerName,
    deptId: row.deptId ?? null,
    loanDate: row.loanDate ?? '',
    dueDate: row.dueDate ?? '',
    purpose: row.purpose,
    remark: row.remark,
    version: row.version,
  })
  loanDialogVisible.value = true
}

async function saveLoan() {
  if (!loanFormRef.value) return
  const ok = await loanFormRef.value.validate().catch(() => false)
  if (!ok) return
  loanSaving.value = true
  try {
    if (loanEditingId.value) await updateToolLoan(loanEditingId.value, { ...loanForm })
    else await createToolLoan({ ...loanForm })
    ElMessage.success(t('common.message.saveSuccess'))
    loanDialogVisible.value = false
    await refreshAll()
    if (currentId.value) await selectTool(currentId.value)
  } catch {
    /* http notifies */
  } finally {
    loanSaving.value = false
  }
}

async function doReturn(row: AssetToolLoan) {
  try {
    await ElMessageBox.confirm(t('asset.tool.returnTip'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await returnToolLoan(row.id)
    ElMessage.success(t('common.message.submitSuccess'))
    await refreshAll()
    if (currentId.value) await selectTool(currentId.value)
  } catch {
    /* http notifies */
  }
}

async function removeLoan(row: AssetToolLoan) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteToolLoan(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    await refreshAll()
    if (currentId.value) await selectTool(currentId.value)
  } catch {
    /* http notifies */
  }
}

</script>

<template>
  <div class="bs-page bs-page--fill tool-page">
    <PageHeader :title="t('asset.tool.title')">
      <template #actions>
        <el-button @click="refreshAll">
          <el-icon><Refresh /></el-icon>
          <span>{{ t('common.action.refresh') }}</span>
        </el-button>
        <el-button v-permission="'asset:tool:create'" type="primary" @click="openToolCreate">
          {{ t('asset.tool.create') }}
        </el-button>
      </template>
    </PageHeader>

    <div class="stat-row">
      <div v-for="card in statCards" :key="card.key" class="stat-card">
        <div class="stat-label">{{ card.label }}</div>
        <div class="stat-value">{{ fmtNumber(card.value) }}</div>
      </div>
    </div>

    <div class="master-detail">
      <section class="bs-page-card master-panel">
        <div class="panel-header">
          <span class="panel-title">{{ t('asset.tool.title') }}</span>
        </div>
        <div class="panel-filters">
          <el-input
            v-model="keyword"
            :placeholder="t('common.form.placeholderSearch')"
            clearable
            class="panel-search"
            @keyup.enter="onSearch"
            @clear="resetSearch"
          />
          <el-select v-model="statusFilter" clearable :placeholder="t('common.form.status')" @change="onSearch">
            <el-option v-for="s in STATUS_OPTIONS" :key="s" :label="t(`asset.status.${s}`)" :value="s" />
          </el-select>
        </div>
        <div v-loading="loading" class="panel-body">
          <div
            v-for="tool in tools"
            :key="tool.id"
            class="master-item"
            :class="{ active: tool.id === currentId }"
            @click="selectTool(tool.id)"
          >
            <div class="master-item-head">
              <div>
                <span class="master-code">{{ tool.toolNo }}</span>
                <span class="master-name">{{ tool.name }}</span>
              </div>
              <ActionBar :actions="toolActions(tool)" @select="(k) => onToolAction(k, tool)" />
            </div>
            <div class="master-item-meta">
              {{ tool.spec || '-' }} · {{ tool.warehouseName || '-' }} · {{ tool.deptName || '-' }}
            </div>
            <div class="master-item-summary">
              <StatusTag :status="tool.status" i18n-prefix="asset.status" />
              <span>{{ t('asset.tool.value') }}: {{ fmtNumber(tool.value) }}</span>
            </div>
          </div>
          <el-empty v-if="!loading && !tools.length" :description="t('common.table.empty')" />
        </div>
      </section>

      <section class="bs-page-card detail-panel">
        <div class="panel-header">
          <span class="panel-title">{{ t('asset.tool.loanTitle') }}</span>
          <el-button
            v-permission="'asset:toolLoan:create'"
            type="primary"
            size="small"
            :disabled="!currentId"
            @click="openLoanCreate"
          >
            {{ t('asset.tool.createLoan') }}
          </el-button>
        </div>
        <div v-loading="loanLoading" class="panel-body panel-body--table">
          <el-table :data="loans" border stripe size="small" height="100%">
            <el-table-column :label="t('asset.tool.loanNo')" prop="loanNo" width="150" />
            <el-table-column :label="t('asset.tool.borrower')" prop="borrowerName" width="110" />
            <el-table-column :label="t('asset.tool.loanDate')" prop="loanDate" width="110" />
            <el-table-column :label="t('asset.tool.dueDate')" prop="dueDate" width="110" />
            <el-table-column :label="t('asset.tool.returnDate')" prop="returnDate" width="110" />
            <el-table-column :label="t('asset.tool.purpose')" prop="purpose" min-width="140" />
            <el-table-column :label="t('common.form.status')" width="100">
              <template #default="{ row }">
                <StatusTag :status="String(row.status)" i18n-prefix="asset.status" />
              </template>
            </el-table-column>
            <el-table-column :label="t('common.action.operate')" width="110" fixed="right" align="center">
              <template #default="{ row }">
                <ActionBar :actions="loanActions(row)" @select="(k) => onLoanAction(k, row)" />
              </template>
            </el-table-column>
          </el-table>
        </div>
      </section>
    </div>

    <el-dialog v-model="toolDialogVisible" :title="toolDialogTitle" width="var(--bs-layout-dialog-lg)" append-to-body>
      <el-form ref="toolFormRef" :model="toolForm" label-width="110px">
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item
              :label="t('asset.tool.toolNo')"
              prop="toolNo"
              :rules="[{ required: true, message: t('common.form.required') }]"
            >
              <el-input v-model="toolForm.toolNo" :maxlength="32" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item
              :label="t('asset.tool.name')"
              prop="name"
              :rules="[{ required: true, message: t('common.form.required') }]"
            >
              <el-input v-model="toolForm.name" :maxlength="128" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.tool.spec')">
              <el-input v-model="toolForm.spec" :maxlength="255" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.tool.model')">
              <el-input v-model="toolForm.model" :maxlength="64" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.tool.category')">
              <el-select v-model="toolForm.category" clearable style="width: 100%">
                <el-option v-for="o in categoryDict.opts.value" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.tool.unit')">
              <el-input v-model="toolForm.unit" :maxlength="16" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.tool.warehouse')">
              <el-select v-model="toolForm.warehouseId" clearable style="width: 100%">
                <el-option v-for="o in warehouseOpts.opts.value" :key="o.value" :label="o.label" :value="o.value" />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.tool.dept')">
              <el-tree-select
                v-model="toolForm.deptId"
                :data="deptTree.deptTree.value"
                :props="{ label: 'name', value: 'id', children: 'children' }"
                check-strictly
                clearable
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.tool.purchaseDate')">
              <el-date-picker v-model="toolForm.purchaseDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.tool.value')">
              <el-input-number v-model="toolForm.value" :min="0" :precision="2" :controls="false" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item :label="t('common.form.status')">
              <el-radio-group v-model="toolForm.status">
                <el-radio v-for="s in STATUS_OPTIONS" :key="s" :value="s">{{ t(`asset.status.${s}`) }}</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('asset.tool.remark')">
          <el-input v-model="toolForm.remark" type="textarea" :rows="2" :maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="toolDialogVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="toolSaving" @click="saveTool">{{ t('common.action.save') }}</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="loanDialogVisible" :title="loanDialogTitle" width="var(--bs-layout-dialog-md)" append-to-body>
      <el-form ref="loanFormRef" :model="loanForm" label-width="110px">
        <el-form-item
          :label="t('asset.toolLoan.tool')"
          prop="toolId"
          :rules="[{ required: true, message: t('common.form.required') }]"
        >
          <el-select v-model="loanForm.toolId" filterable style="width: 100%">
            <el-option
              v-for="tool in tools"
              :key="tool.id"
              :label="`${tool.toolNo} ${tool.name}`"
              :value="tool.id"
            />
          </el-select>
        </el-form-item>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item :label="t('asset.tool.borrower')">
              <el-input v-model="loanForm.borrowerName" :maxlength="64" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.toolLoan.dept')">
              <el-tree-select
                v-model="loanForm.deptId"
                :data="deptTree.deptTree.value"
                :props="{ label: 'name', value: 'id', children: 'children' }"
                check-strictly
                clearable
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.tool.loanDate')">
              <el-date-picker v-model="loanForm.loanDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('asset.tool.dueDate')">
              <el-date-picker v-model="loanForm.dueDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-form-item :label="t('asset.tool.purpose')">
          <el-input v-model="loanForm.purpose" type="textarea" :rows="2" :maxlength="500" />
        </el-form-item>
        <el-form-item :label="t('asset.toolLoan.remark')">
          <el-input v-model="loanForm.remark" type="textarea" :rows="2" :maxlength="500" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="loanDialogVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="loanSaving" @click="saveLoan">{{ t('common.action.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.tool-page {
  gap: var(--bs-layout-section-gap);
}

.stat-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--bs-space-3);
  flex-shrink: 0;
}

.stat-card {
  background: var(--bs-color-bg-surface);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  padding: var(--bs-space-3);
}

.stat-label {
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-xs);
}

.stat-value {
  margin-top: var(--bs-space-2);
  font-size: 24px;
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.master-detail {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: minmax(300px, 380px) 1fr;
  gap: var(--bs-layout-section-gap);
}

.master-panel,
.detail-panel {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  min-height: 0;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bs-space-2);
  flex-shrink: 0;
}

.panel-filters {
  display: flex;
  gap: var(--bs-space-2);
  flex-shrink: 0;
}

.panel-search {
  flex: 1;
  min-width: 0;
}

.panel-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.panel-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.panel-body--table {
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.master-item {
  padding: var(--bs-space-2) var(--bs-space-3);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  margin-bottom: var(--bs-space-2);
  cursor: pointer;
}

.master-item:hover {
  border-color: var(--bs-color-border-default);
}

.master-item.active {
  border-color: var(--bs-color-primary);
  background: var(--bs-color-brand-primary-soft);
}

.master-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bs-space-2);
}

.master-code {
  font-family: var(--bs-typography-font-family-mono);
  color: var(--bs-color-fg-muted);
  margin-right: var(--bs-space-2);
}

.master-name {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.master-item-meta {
  margin-top: var(--bs-space-1);
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
}

.master-item-summary {
  margin-top: var(--bs-space-2);
  display: flex;
  align-items: center;
  gap: var(--bs-space-3);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}
</style>
