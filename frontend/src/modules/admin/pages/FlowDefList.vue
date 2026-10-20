<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import FlowChainDesigner from '@/components/flow/FlowChainDesigner.vue'
import OaFormPanel from '@/modules/admin/components/OaFormPanel.vue'
import { isOrgApproverType, normalizeNode, validateFlowNodes, type FlowNodeRow } from '@/components/flow/flowModel'
import { listFlowDefs, createFlowDef, updateFlowDef, deleteFlowDef, listRoles, listUsers } from '@/api/admin'
import { listOaForms } from '@/api/oa'
import { previewFlow } from '@/api/approval'
import type { FlowApproverType, FlowDef, FlowGraphData, FlowNodeType } from '@/api/types'

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
})

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
      name: form.name,
      bizType: form.bizType,
      enabled: form.enabled,
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
      })),
    }
    // 竖链模式：由节点行自动生成 LogicFlow 兼容图（自动纵向布局）随节点行一并提交
    if (mode.value === 'chain' && designerRef.value) {
      payload.processGraph = designerRef.value.exportGraph()
    }
    if (editingId.value) await updateFlowDef(editingId.value, payload)
    else await createFlowDef(payload)
    ElMessage.success(t('common.message.saveSuccess'))
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

async function remove(row: FlowDef) {
  try {
    await ElMessageBox.confirm(t('admin.flow.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteFlowDef(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    void load()
  } catch {
    /* http notifies */
  }
}
</script>

<template>
  <ListPage :title="t('admin.flow.title')" :loading="activeTab === 'defs' ? loading : false">
    <template #actions>
      <template v-if="activeTab === 'defs'">
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
      <el-table v-if="activeTab === 'defs'" :data="items" row-key="id" border stripe height="100%">
        <el-table-column :label="t('admin.flow.code')" prop="code" width="130" />
        <el-table-column :label="t('admin.flow.name')" prop="name" min-width="150" />
        <el-table-column :label="t('admin.flow.bizType')" width="110">
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
        <el-table-column :label="t('admin.flow.enabled')" width="90">
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
              :type="n.nodeType === 'condition' ? 'warning' : n.nodeType === 'cc' ? 'info' : 'primary'"
            >
              {{ n.seq }}. {{ n.nodeName }}
              <template v-if="(n.nodeType ?? 'approval') === 'approval'">
                ({{ approverTypeLabel(n.approverType) }}<template v-if="n.approverName || n.approverValue">: {{ n.approverName || n.approverValue }}</template>)
              </template>
              <template v-else>({{ nodeTypeLabel(n.nodeType) }})</template>
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.action.operate')" width="150" fixed="right">
          <template #default="{ row }">
            <el-button v-permission="'admin:flow:edit'" link type="primary" @click="openEdit(row as FlowDef)">
              {{ t('common.action.edit') }}
            </el-button>
            <el-button v-permission="'admin:flow:edit'" link type="danger" @click="remove(row as FlowDef)">
              {{ t('common.action.delete') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <OaFormPanel v-else @goto-def="gotoDef" />
    </template>
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" :width="mode === 'chain' ? '1080px' : '720px'" append-to-body>
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
        />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="previewVisible" :title="t('admin.flow.preview')" width="480px" append-to-body>
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

.preview-route {
  margin-top: var(--bs-space-2);
  word-break: break-all;
}
</style>
