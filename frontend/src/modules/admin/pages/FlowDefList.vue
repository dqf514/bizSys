<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import FlowChainDesigner from '@/components/flow/FlowChainDesigner.vue'
import OaFormPanel from '@/modules/admin/components/OaFormPanel.vue'
import { isOrgApproverType, normalizeNode, validateFlowNodes, type FlowNodeRow } from '@/components/flow/flowModel'
import { listFlowDefs, createFlowDef, updateFlowDef, deleteFlowDef, listRoles, listUsers } from '@/api/admin'
import { listOaForms } from '@/api/oa'
import { aiSuggestFlow, previewFlow, type FlowSuggestResult } from '@/api/approval'
import { useAiCapabilities } from '@/composables/useAiCapabilities'
import type {
  FlowApproverType,
  FlowDef,
  FlowDefinitionOptions,
  FlowGraphData,
  FlowNode,
  FlowNodeType,
} from '@/api/types'

defineOptions({ name: 'FlowDefList' })

const { t } = useI18n()

/* ---------- 双页签：流程定义 / OA 表单设计 ---------- */
const activeTab = ref<'defs' | 'forms'>('defs')
const pageTabs = computed<StatusTabItem[]>(() => [
  { value: 'defs', labelKey: 'oa.design.tabDefs' },
  { value: 'forms', labelKey: 'oa.design.tabForms' },
])

const items = ref<FlowDef[]>([])
const loading = ref(false)
/** 本地全量列表：前端关键词过滤（code/name） */
const defKeyword = ref('')
const filteredItems = computed(() => {
  const kw = defKeyword.value.trim().toLowerCase()
  if (!kw) return items.value
  return items.value.filter(
    (x) => x.code?.toLowerCase().includes(kw) || x.name?.toLowerCase().includes(kw),
  )
})
/** flowDefinitionId → 绑定的 OA 表单名（绑定信息反查） */
const boundForms = ref<Map<number, string[]>>(new Map())

async function load() {
  loading.value = true
  try {
    const data = await listFlowDefs()
    items.value = Array.isArray(data) ? data : (data.items ?? [])
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

async function loadBoundForms() {
  try {
    const forms = await listOaForms()
    const m = new Map<number, string[]>()
    for (const f of forms) {
      if (!f.flowDefinitionId) continue
      m.set(f.flowDefinitionId, [...(m.get(f.flowDefinitionId) ?? []), `${f.name} v${f.formVersion}`])
    }
    boundForms.value = m
  } catch {
    /* 无 oa:admin:design 权限时静默，绑定列退化为 bizType 标签 */
  }
}

onMounted(() => {
  void load()
  void loadBoundForms()
})

const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const mode = ref<'simple' | 'chain'>('simple')
const designerRef = ref<InstanceType<typeof FlowChainDesigner> | null>(null)
const form = reactive({
  code: '',
  name: '',
  bizType: 'contract',
  enabled: true,
  nodes: [] as FlowNodeRow[],
  processGraph: null as FlowGraphData | null,
  /** 流程变量声明（FORM_* 审批人类型的变量名必须在其中声明） */
  variables: [] as { key: string; label: string }[],
  /** 流程通用选项（未勾选 = 保持系统默认行为） */
  options: {} as FlowDefinitionOptions,
})

/** 流程通用选项开关清单（对应后端 ApprovalDefinition.options 的 10 个键） */
const OPTION_KEYS: (keyof FlowDefinitionOptions)[] = [
  'commentRequired',
  'commentSignRequired',
  'allowAddSign',
  'allowWithdrawAfterApproved',
  'allowModifyFlow',
  'allowModifyCc',
  'executorCommentRequired',
  'executorCanModify',
  'allowProxySubmit',
  'detailTablePermission',
]

const variableKeys = computed(() => form.variables.map((v) => v.key.trim()).filter(Boolean))

function addVariable() {
  form.variables.push({ key: '', label: '' })
}

function removeVariable(idx: number) {
  form.variables.splice(idx, 1)
}

const roleOptions = ref<{ id: number; name: string; code?: string }[]>([])
const userOptions = ref<{ id: number; name: string }[]>([])

async function loadApprovers() {
  try {
    const roles = await listRoles({ page: 1, size: 100 })
    roleOptions.value = (roles.items ?? []).map((r) => ({ id: r.id, name: r.name, code: r.code }))
  } catch {
    roleOptions.value = []
  }
  try {
    const users = await listUsers({ page: 1, size: 100 })
    userOptions.value = (users.items ?? []).map((u) => ({ id: u.id, name: u.name || u.username }))
  } catch {
    userOptions.value = []
  }
}

function blankNode(seq: number): FlowNodeRow {
  return normalizeNode({ seq, nodeName: '', nodeType: 'approval', approverType: 'USER', approverValue: '' })
}

function addNode() {
  form.nodes.push(blankNode(form.nodes.length + 1))
  reseq()
}

function removeNode(idx: number) {
  form.nodes.splice(idx, 1)
  reseq()
}

function moveNode(idx: number, dir: -1 | 1) {
  const target = idx + dir
  if (target < 0 || target >= form.nodes.length) return
  const a = form.nodes[idx]!
  const b = form.nodes[target]!
  form.nodes[idx] = b
  form.nodes[target] = a
  reseq()
}

function reseq() {
  form.nodes.forEach((n, i) => {
    n.seq = i + 1
  })
}

function hasAdvancedNodes() {
  return form.nodes.some((n) => n.nodeType !== 'approval')
}

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('admin.flow.create')
  Object.assign(form, {
    code: '',
    name: '',
    bizType: 'contract',
    enabled: true,
    nodes: [blankNode(1)],
    processGraph: null,
    variables: [],
    options: {},
  })
  mode.value = 'simple'
  dialogVisible.value = true
  void loadApprovers()
}

function openEdit(row: FlowDef) {
  editingId.value = row.id
  dialogTitle.value = t('admin.flow.edit')
  Object.assign(form, {
    code: row.code,
    name: row.name,
    bizType: row.bizType,
    enabled: Boolean(row.enabled),
    nodes: (row.nodes ?? []).map((n) => normalizeNode({ ...n })),
    processGraph: row.processGraph ?? null,
    variables: Object.entries(row.variablesSchema ?? {}).map(([key, v]) => ({
      key,
      label:
        v && typeof v === 'object' && 'label' in v
          ? String((v as { label?: unknown }).label ?? key)
          : String(v ?? key),
    })),
    options: { ...(row.options ?? {}) },
  })
  if (!form.nodes.length) form.nodes.push(blankNode(1))
  // 含条件/抄送节点的定义只能竖链模式编辑（简易表格无法表达分支）
  mode.value = hasAdvancedNodes() ? 'chain' : 'simple'
  dialogVisible.value = true
  void loadApprovers()
}

// --- 分支预演 ---

const previewVisible = ref(false)
const previewVariables = ref('{}')
const previewLoading = ref(false)
const previewRoute = ref<string>('')

async function runPreview() {
  let variables: Record<string, unknown>
  try {
    variables = JSON.parse(previewVariables.value || '{}') as Record<string, unknown>
  } catch {
    ElMessage.warning(t('admin.flow.previewBadJson'))
    return
  }
  previewLoading.value = true
  try {
    const data = await previewFlow(form.code || 'draft', variables, form.nodes)
    previewRoute.value = (data.route ?? []).map((n) => `${n.seq}. ${n.nodeName}`).join(' → ')
  } catch {
    previewRoute.value = ''
  } finally {
    previewLoading.value = false
  }
}

// --- AI 建议审批链（建议 → 人工采纳才改写节点，不自动落库） ---

const aiCaps = useAiCapabilities()
const suggestOn = computed(() => aiCaps.featureOn('flow_route'))
const suggestVisible = ref(false)
const suggestLoading = ref(false)
const suggestResult = ref<FlowSuggestResult | null>(null)
const suggestAmount = ref<number | undefined>(undefined)
const suggestCategory = ref('')

onMounted(() => void aiCaps.ensureLoaded())

async function runSuggest() {
  suggestLoading.value = true
  try {
    suggestResult.value = await aiSuggestFlow({
      bizType: form.bizType,
      name: form.name,
      amount: suggestAmount.value ?? null,
      category: suggestCategory.value,
    })
  } catch {
    suggestResult.value = null
  } finally {
    suggestLoading.value = false
  }
}

function adoptSuggest() {
  const nodes = suggestResult.value?.nodes ?? []
  if (!nodes.length) return
  form.nodes = nodes.map((n, i) =>
    normalizeNode({
      seq: i + 1,
      nodeName: n.nodeName,
      nodeType: 'approval',
      signMode: (n.signMode === 'and' ? 'and' : 'or') as FlowNode['signMode'],
      approverType: n.approverType as FlowNode['approverType'],
      approverValue: n.approverType === 'USER' && /^\d+$/.test(n.approverValue) ? Number(n.approverValue) : n.approverValue,
      approverName: n.approverName,
    }),
  )
  mode.value = 'simple'
  suggestVisible.value = false
  ElMessage.success(t('admin.flow.aiSuggestAdopted'))
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  if (mode.value === 'simple' && hasAdvancedNodes()) {
    ElMessage.warning(t('admin.flow.advancedOnlyChain'))
    return
  }
  const errors = mode.value === 'chain' ? (designerRef.value?.validate() ?? []) : validateFlowNodes(form.nodes)
  if (errors.length) {
    ElMessage.warning(errors.map((k) => t(k)).join('；'))
    return
  }
  saving.value = true
  try {
    const payload: Record<string, unknown> = {
      code: form.code,
      variablesSchema: Object.fromEntries(
        form.variables
          .filter((v) => v.key.trim())
          .map((v) => [v.key.trim(), { type: 'string', label: v.label || v.key.trim() }]),
      ),
      name: form.name,
      bizType: form.bizType,
      enabled: form.enabled,
      options: form.options,
      nodes: form.nodes.map((n, i) => ({
        seq: i + 1,
        nodeName: n.nodeName,
        nodeType: n.nodeType,
        signMode: n.signMode,
        approverType: n.approverType,
        approverValue: String(n.approverValue ?? ''),
        approverName: n.approverName ?? '',
        chainLevels: n.approverType === 'SUPERVISOR_CHAIN' ? (n.chainLevels ?? 0) : null,
        branches: n.nodeType === 'condition' ? (n.branches ?? []) : null,
        defaultSeq: n.nodeType === 'condition' ? n.defaultSeq : null,
        fieldPermissions:
          n.fieldPermissions && Object.keys(n.fieldPermissions).length ? { ...n.fieldPermissions } : null,
      })),
    }
    // 竖链模式：由节点行自动生成 LogicFlow 兼容图（自动纵向布局）随节点行一并提交
    if (mode.value === 'chain' && designerRef.value) {
      payload.processGraph = designerRef.value.exportGraph()
    }
    if (editingId.value) {
      const res = await updateFlowDef(editingId.value, payload)
      if (res?.newVersion) {
        ElMessage.success(
          t('admin.flow.savedAsNewVersion', { version: res.version, count: res.runningCount }),
        )
      } else {
        ElMessage.success(t('common.message.saveSuccess'))
      }
    } else {
      await createFlowDef(payload)
      ElMessage.success(t('common.message.saveSuccess'))
    }
    dialogVisible.value = false
    void load()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

function onApproverChange(node: FlowNodeRow, v: unknown) {
  if (isOrgApproverType(node.approverType)) {
    // 组织类型：approverValue 存兜底角色 code
    node.approverName = roleOptions.value.find((x) => (x.code ?? String(x.id)) === String(v))?.name ?? ''
    return
  }
  const list = node.approverType === 'ROLE' ? roleOptions.value : userOptions.value
  node.approverName = list.find((x) => String(x.id) === String(v))?.name ?? ''
}

function onApproverTypeChange(node: FlowNodeRow, v: FlowApproverType) {
  node.approverType = v
  node.approverValue = ''
  node.approverName = ''
  if (v === 'SUPERVISOR_CHAIN' && node.chainLevels == null) node.chainLevels = 0
}

function bizLabel(b: string) {
  if (b === 'contract') return t('admin.flow.bizContract')
  if (b === 'task') return t('admin.flow.bizTask')
  if (b === 'report') return t('admin.flow.bizReport')
  if (b === 'invoice') return t('admin.flow.bizInvoice')
  if (b === 'oa') return t('admin.flow.bizOa')
  return b
}

function approverTypeLabel(at?: string) {
  const key =
    at === 'ROLE'
      ? 'admin.flow.approverRole'
      : at === 'DEPT_LEADER'
        ? 'admin.flow.approverDeptLeader'
        : at === 'PARENT_DEPT_LEADER'
          ? 'admin.flow.approverParentDeptLeader'
          : at === 'SUPERVISOR_CHAIN'
            ? 'admin.flow.approverSupervisorChain'
            : 'admin.flow.approverUser'
  return t(key)
}

/** OA 表单设计页签"去设计"：切回流程定义页签并打开该定义 */
function gotoDef(flowDefinitionId: number) {
  activeTab.value = 'defs'
  const row = items.value.find((x) => x.id === flowDefinitionId)
  if (row) openEdit(row)
}

function nodeTypeLabel(nt?: FlowNodeType) {
  return t(`admin.flow.nodeType.${nt ?? 'approval'}`)
}

/** 历史版本：同 code 存在更高版本（旧版只读查看，仍供存量实例流转） */
function isHistory(row: FlowDef) {
  return (row.latestVersion ?? row.version ?? 1) > (row.version ?? 1)
}

async function remove(row: FlowDef) {
  try {
    await ElMessageBox.confirm(t('admin.flow.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    const res = await deleteFlowDef(row.id)
    if (res?.disabled) ElMessage.warning(t('admin.flow.deleteDisabledInstead'))
    else ElMessage.success(t('common.message.deleteSuccess'))
    void load()
  } catch {
    /* http notifies */
  }
}

const defActions: ActionItem[] = [
  { key: 'edit', tip: 'common.action.edit', perm: 'admin:flow:edit' },
  { key: 'delete', tip: 'common.action.delete', perm: 'admin:flow:edit' },
]

function onDefAction(key: string, row: FlowDef) {
  if (key === 'edit') openEdit(row)
  else if (key === 'delete') void remove(row)
}
</script>

<template>
  <ListPage :title="t('admin.flow.title')" :loading="activeTab === 'defs' ? loading : false">
    <template #actions>
      <template v-if="activeTab === 'defs'">
        <el-input
          v-model="defKeyword"
          :placeholder="t('common.form.placeholderSearch')"
          :prefix-icon="Search"
          clearable
          class="local-filter"
        />
        <el-button v-permission="'admin:flow:edit'" type="primary" @click="openCreate">
          {{ t('admin.flow.create') }}
        </el-button>
        <el-button @click="load()">{{ t('common.action.refresh') }}</el-button>
      </template>
    </template>

    <template #statusTabs>
      <StatusTabs :tabs="pageTabs" :model-value="activeTab" @update:model-value="activeTab = $event as 'defs' | 'forms'" />
    </template>

    <template #table>
      <el-table v-if="activeTab === 'defs'" :data="filteredItems" row-key="id" border stripe height="100%">
        <el-table-column :label="t('admin.flow.code')" prop="code" width="130" sortable />
        <el-table-column :label="t('admin.flow.version')" prop="version" width="120" sortable>
          <template #default="{ row }">
            <span :class="{ muted: isHistory(row as FlowDef) }">v{{ (row as FlowDef).version ?? 1 }}</span>
            <el-tag v-if="isHistory(row as FlowDef)" type="info" size="small" effect="plain" class="node-tag">
              {{ t('admin.flow.historyVersion') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.flow.name')" prop="name" min-width="150" sortable />
        <el-table-column :label="t('admin.flow.bizType')" prop="bizType" width="110" sortable>
          <template #default="{ row }">{{ bizLabel(row.bizType) }}</template>
        </el-table-column>
        <el-table-column :label="t('oa.design.boundTo')" min-width="150">
          <template #default="{ row }">
            <template v-if="boundForms.get(row.id)?.length">
              <el-tag v-for="n in boundForms.get(row.id)" :key="n" size="small" class="node-tag" type="success">
                {{ t('oa.design.boundForm', { name: n }) }}
              </el-tag>
            </template>
            <span v-else class="muted">-</span>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.flow.enabled')" prop="enabled" width="90" sortable>
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'" size="small">
              {{ row.enabled ? t('common.form.enabled') : t('common.form.disabled') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.flow.nodes')" min-width="260">
          <template #default="{ row }">
            <el-tag
              v-for="n in (row.nodes || [])"
              :key="n.seq"
              size="small"
              class="node-tag"
              :type="
                n.nodeType === 'condition'
                  ? 'warning'
                  : n.nodeType === 'cc'
                    ? 'info'
                    : n.nodeType === 'executor'
                      ? 'success'
                      : 'primary'
              "
            >
              {{ n.seq }}. {{ n.nodeName }}
              <template v-if="(n.nodeType ?? 'approval') === 'approval'">
                ({{ approverTypeLabel(n.approverType) }}<template v-if="n.approverName || n.approverValue">: {{ n.approverName || n.approverValue }}</template>)
              </template>
              <template v-else>({{ nodeTypeLabel(n.nodeType) }})</template>
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.action.operate')" width="90" fixed="right" align="center" header-align="center">
          <template #default="{ row }">
            <ActionBar :actions="defActions" @select="(key: string) => onDefAction(key, row as FlowDef)" />
          </template>
        </el-table-column>
      </el-table>

      <OaFormPanel v-else @goto-def="gotoDef" />
    </template>
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" :width="mode === 'chain' ? 'var(--bs-layout-dialog-xl)' : 'var(--bs-layout-dialog-lg)'" append-to-body>
    <el-form ref="formRef" :model="form" label-width="110px">
      <el-form-item :label="t('admin.flow.code')" prop="code" :rules="[{ required: true, message: t('common.form.required') }]">
        <el-input v-model="form.code" :disabled="Boolean(editingId)" />
      </el-form-item>
      <el-form-item :label="t('admin.flow.name')" prop="name" :rules="[{ required: true, message: t('common.form.required') }]">
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item :label="t('admin.flow.bizType')">
        <el-select v-model="form.bizType" style="width: 100%">
          <el-option :label="t('admin.flow.bizContract')" value="contract" />
          <el-option :label="t('admin.flow.bizTask')" value="task" />
          <el-option :label="t('admin.flow.bizReport')" value="report" />
          <el-option :label="t('admin.flow.bizInvoice')" value="invoice" />
          <el-option :label="t('admin.flow.bizOa')" value="oa" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('admin.flow.enabled')">
        <el-switch v-model="form.enabled" />
      </el-form-item>

      <el-form-item :label="t('admin.flow.editMode')">
        <el-radio-group v-model="mode">
          <el-radio-button value="simple">{{ t('admin.flow.modeSimple') }}</el-radio-button>
          <el-radio-button value="chain">{{ t('admin.flow.modeChain') }}</el-radio-button>
        </el-radio-group>
        <el-button class="preview-btn" size="small" @click="previewVisible = true">
          {{ t('admin.flow.preview') }}
        </el-button>
        <el-button
          v-if="suggestOn"
          class="preview-btn"
          size="small"
          type="primary"
          plain
          @click="suggestVisible = true"
        >
          {{ t('admin.flow.aiSuggest') }}
        </el-button>
      </el-form-item>

      <el-form-item v-if="mode === 'simple'" :label="t('admin.flow.nodes')">
        <div class="node-editor">
          <div v-for="(node, idx) in form.nodes" :key="idx" class="node-row">
            <span class="node-seq">{{ idx + 1 }}</span>
            <el-input v-model="node.nodeName" :placeholder="t('admin.flow.nodeName')" class="node-name" />
            <el-select v-model="node.approverType" class="node-type" @change="onApproverTypeChange(node, $event as FlowApproverType)">
              <el-option :label="t('admin.flow.approverUser')" value="USER" />
              <el-option :label="t('admin.flow.approverRole')" value="ROLE" />
              <el-option :label="t('admin.flow.approverDeptLeader')" value="DEPT_LEADER" />
              <el-option :label="t('admin.flow.approverParentDeptLeader')" value="PARENT_DEPT_LEADER" />
              <el-option :label="t('admin.flow.approverSupervisorChain')" value="SUPERVISOR_CHAIN" />
            </el-select>
            <el-input-number
              v-if="node.approverType === 'SUPERVISOR_CHAIN'"
              :model-value="node.chainLevels ?? 0"
              :min="0"
              :max="20"
              class="node-chain"
              @update:model-value="node.chainLevels = Number($event ?? 0)"
            />
            <el-select
              v-if="isOrgApproverType(node.approverType)"
              v-model="node.approverValue"
              class="node-value"
              filterable
              clearable
              :placeholder="t('admin.flow.orgFallbackRole')"
              @change="onApproverChange(node, $event)"
            >
              <el-option
                v-for="opt in roleOptions"
                :key="opt.id"
                :label="opt.name"
                :value="opt.code ?? String(opt.id)"
              />
            </el-select>
            <el-select
              v-else
              v-model="node.approverValue"
              class="node-value"
              filterable
              :placeholder="t('admin.flow.approverValue')"
              @change="onApproverChange(node, $event)"
            >
              <el-option
                v-for="opt in (node.approverType === 'ROLE' ? roleOptions : userOptions)"
                :key="opt.id"
                :label="opt.name"
                :value="opt.id"
              />
            </el-select>
            <el-button @click="moveNode(idx, -1)">{{ t('admin.flow.moveUp') }}</el-button>
            <el-button @click="moveNode(idx, 1)">{{ t('admin.flow.moveDown') }}</el-button>
            <el-button type="danger" link @click="removeNode(idx)">{{ t('common.action.delete') }}</el-button>
          </div>
          <el-button type="primary" plain @click="addNode">{{ t('admin.flow.addNode') }}</el-button>
        </div>
      </el-form-item>

      <el-form-item v-else :label="t('admin.flow.nodes')">
        <FlowChainDesigner
          v-if="dialogVisible"
          ref="designerRef"
          v-model:nodes="form.nodes"
          :user-options="userOptions"
          :role-options="roleOptions"
          :variable-keys="variableKeys"
        />
      </el-form-item>

      <el-form-item :label="t('admin.flow.variables')">
        <div class="variable-list">
          <div v-for="(v, idx) in form.variables" :key="idx" class="variable-row">
            <el-input v-model="v.key" :placeholder="t('admin.flow.variableKey')" class="variable-key" />
            <el-input v-model="v.label" :placeholder="t('admin.flow.variableLabel')" class="variable-label" />
            <el-button link type="danger" @click="removeVariable(idx)">
              {{ t('common.action.delete') }}
            </el-button>
          </div>
          <el-button size="small" plain @click="addVariable">
            {{ t('admin.flow.addVariable') }}
          </el-button>
          <div class="field-tip">{{ t('admin.flow.variablesTip') }}</div>
        </div>
      </el-form-item>

      <el-form-item :label="t('admin.flow.options')">
        <div class="option-list">
          <div v-for="key in OPTION_KEYS" :key="key" class="option-row">
            <span class="option-label">{{ t(`admin.flow.option.${key}`) }}</span>
            <el-switch
              :model-value="Boolean(form.options[key])"
              @update:model-value="form.options[key] = Boolean($event)"
            />
          </div>
          <div class="field-tip">{{ t('admin.flow.optionsTip') }}</div>
        </div>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="suggestVisible" :title="t('admin.flow.aiSuggest')" width="var(--bs-layout-dialog-md)" append-to-body>
    <el-form label-position="top" size="small">
      <el-form-item :label="t('admin.flow.aiSuggestAmount')">
        <el-input-number v-model="suggestAmount" :min="0" :precision="2" class="suggest-amount" />
      </el-form-item>
      <el-form-item :label="t('admin.flow.aiSuggestCategory')">
        <el-input v-model="suggestCategory" maxlength="64" />
      </el-form-item>
    </el-form>
    <div v-if="suggestResult" class="suggest-result">
      <div v-for="(n, i) in suggestResult.nodes" :key="i" class="suggest-node">
        <span class="node-seq">{{ i + 1 }}</span>
        <span class="suggest-node-name">{{ n.nodeName }}</span>
        <el-tag size="small" type="primary">
          {{ approverTypeLabel(n.approverType) }}<template v-if="n.approverName || n.approverValue">: {{ n.approverName || n.approverValue }}</template>
        </el-tag>
        <el-tag v-if="n.signMode === 'and'" size="small" type="warning">{{ t('admin.flow.aiSuggestSignAll') }}</el-tag>
      </div>
      <el-alert v-if="suggestResult.rationale" type="info" :closable="false" class="preview-route">
        {{ suggestResult.rationale }}
      </el-alert>
    </div>
    <template #footer>
      <el-button @click="suggestVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button :loading="suggestLoading" @click="runSuggest">{{ t('admin.flow.aiSuggestRun') }}</el-button>
      <el-button type="primary" :disabled="!suggestResult?.nodes.length" @click="adoptSuggest">
        {{ t('admin.flow.aiSuggestAdopt') }}
      </el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="previewVisible" :title="t('admin.flow.preview')" width="var(--bs-layout-dialog-sm)" append-to-body>
    <el-form label-position="top" size="small">
      <el-form-item :label="t('admin.flow.previewVariables')">
        <el-input v-model="previewVariables" type="textarea" :rows="4" placeholder='{"amount": 200000}' />
      </el-form-item>
    </el-form>
    <el-alert v-if="previewRoute" type="success" :closable="false" class="preview-route">
      {{ previewRoute }}
    </el-alert>
    <template #footer>
      <el-button @click="previewVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="previewLoading" @click="runPreview">
        {{ t('admin.flow.previewRun') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.muted {
  color: var(--bs-color-fg-muted);
}

.variable-list {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.variable-row {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.variable-key {
  width: 180px;
}

.variable-label {
  flex: 1;
  min-width: 0;
}

.field-tip {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.option-list {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-1);
}

.option-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bs-space-2);
  padding: 2px 0;
}

.option-label {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-default);
}

.node-chain {
  width: 90px;
}

.node-tag {
  margin: 2px 4px 2px 0;
}

.node-editor {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.node-row {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  flex-wrap: wrap;
}

.node-seq {
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--bs-radius-full);
  background: var(--bs-color-fill-light);
  font-size: var(--bs-typography-font-size-xs);
}

.node-name {
  width: 150px;
}

.node-type {
  width: 110px;
}

.node-value {
  width: 150px;
}

.preview-btn {
  margin-left: var(--bs-space-3);
}

.suggest-amount {
  width: 200px;
}

.suggest-result {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  margin-top: var(--bs-space-2);
}

.suggest-node {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.suggest-node-name {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.preview-route {
  margin-top: var(--bs-space-2);
  word-break: break-all;
}

.local-filter {
  width: 220px;
}
</style>
