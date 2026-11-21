<script setup lang="ts">
/**
 * 任务扩展面板（B5 CSV 19–21）：工序流转 / 七维分配 / 全过程追溯 / 操作流程图。
 *
 * - 工序：同一任务同一时刻只允许一道工序进行中（后端强制），当前工序自动高亮；
 * - 七维分配：人 / 机 / 料 / 法 / 环 / 测 / 安，排程域按 equipment·person·vehicle 时段独占与 material 数量占用读取；
 * - 追溯：任务输入 → 报告输出 / 样车归还 / 模型车发运 → 验收 / 结算；
 * - 流程图：工序节点 + 追溯节点合并渲染成链路。
 */
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import { useDictOptions } from '@/composables/useDict'
import {
  createAssignment,
  createProcess,
  createTrace,
  deleteAssignment,
  deleteProcess,
  deleteTrace,
  finishProcess,
  listAssignments,
  listProcesses,
  listTraces,
  operationFlow,
  skipProcess,
  startProcess,
  updateAssignment,
  updateProcess,
} from '@/api/task'
import type { OperationFlow, TaskAssignment, TaskProcess, TaskTrace } from '@/api/types'

defineOptions({ name: 'TaskProcessPanel' })

const props = defineProps<{
  taskId: number
}>()

const emit = defineEmits<{
  /** 工序 / 分配 / 追溯任一变更后触发，供外层刷新任务详情 */
  (e: 'changed'): void
}>()

const { t } = useI18n()
const processOpts = useDictOptions('task_process')
const dimensionOpts = useDictOptions('task_dimension')

/** 追溯节点（固定语义，后端 dict 未登记） */
const TRACE_NODES = [
  { value: 'input', labelKey: 'task.process.nodeInput' },
  { value: 'output_report', labelKey: 'task.process.nodeOutputReport' },
  { value: 'vehicle_return', labelKey: 'task.process.nodeVehicleReturn' },
  { value: 'model_ship', labelKey: 'task.process.nodeModelShip' },
  { value: 'accept', labelKey: 'task.process.nodeAccept' },
  { value: 'settle', labelKey: 'task.process.nodeSettle' },
]

const PROCESS_STATUS_KEYS: Record<string, string> = {
  pending: 'task.process.statusPending',
  running: 'task.process.statusRunning',
  done: 'task.process.statusDone',
  skipped: 'task.process.statusSkipped',
}

const ASSIGN_STATUS_KEYS: Record<string, string> = {
  pending: 'task.process.assignStatusPending',
  allocated: 'task.process.assignStatusAllocated',
  confirmed: 'task.process.assignStatusConfirmed',
  rejected: 'task.process.assignStatusRejected',
}

const activeTab = ref('processes')
const loading = ref(false)

const processes = ref<TaskProcess[]>([])
const assignments = ref<TaskAssignment[]>([])
const traces = ref<TaskTrace[]>([])
const flow = ref<OperationFlow | null>(null)

async function loadAll() {
  if (!props.taskId) return
  loading.value = true
  try {
    const [p, a, tr, f] = await Promise.all([
      listProcesses(props.taskId),
      listAssignments(props.taskId),
      listTraces(props.taskId),
      operationFlow(props.taskId),
    ])
    processes.value = p.items ?? []
    assignments.value = a.items ?? []
    traces.value = tr.items ?? []
    flow.value = f
  } catch {
    processes.value = []
    assignments.value = []
    traces.value = []
    flow.value = null
  } finally {
    loading.value = false
  }
}

watch(() => props.taskId, () => void loadAll(), { immediate: true })

/* ---------------- 工序 ---------------- */

const processDialog = reactive({ visible: false, id: 0 })
const processForm = reactive({
  seq: 0,
  processCode: '',
  processName: '',
  plannedStart: '',
  plannedEnd: '',
  operatorName: '',
  deptName: '',
  remark: '',
})

function openProcess(row?: TaskProcess) {
  processForm.seq = row?.seq ?? 0
  processForm.processCode = row?.processCode ?? ''
  processForm.processName = row?.processName ?? ''
  processForm.plannedStart = row?.plannedStart ?? ''
  processForm.plannedEnd = row?.plannedEnd ?? ''
  processForm.operatorName = row?.operatorName ?? ''
  processForm.deptName = row?.deptName ?? ''
  processForm.remark = row?.remark ?? ''
  processDialog.id = row?.id ?? 0
  processDialog.visible = true
}

async function saveProcess() {
  if (!processForm.processCode) {
    ElMessage.warning(t('common.form.placeholderSelect'))
    return
  }
  const payload = {
    seq: processForm.seq || undefined,
    processCode: processForm.processCode,
    processName: processForm.processName,
    plannedStart: processForm.plannedStart || undefined,
    plannedEnd: processForm.plannedEnd || undefined,
    operatorName: processForm.operatorName,
    deptName: processForm.deptName,
    remark: processForm.remark,
  }
  try {
    if (processDialog.id) await updateProcess(processDialog.id, payload)
    else await createProcess(props.taskId, payload)
    ElMessage.success(t('common.message.saveSuccess'))
    processDialog.visible = false
    void loadAll()
    emit('changed')
  } catch {
    /* http notifies */
  }
}

function processActions(row: TaskProcess): ActionItem[] {
  const actions: ActionItem[] = []
  if (row.status === 'pending') {
    actions.push({ key: 'start', tip: 'task.process.startProcess', perm: 'task:process:edit' })
    actions.push({ key: 'skip', tip: 'task.process.skipProcess', perm: 'task:process:edit' })
  }
  if (row.status === 'running') {
    actions.push({ key: 'finish', tip: 'task.process.finishProcess', perm: 'task:process:edit' })
  }
  if (row.status !== 'done' && row.status !== 'skipped') {
    actions.push({ key: 'edit', tip: 'common.action.edit', perm: 'task:process:edit' })
  }
  if (row.status !== 'running') {
    actions.push({ key: 'delete', tip: 'common.action.delete', perm: 'task:process:edit', danger: true })
  }
  return actions
}

async function onProcessAction(key: string, row: TaskProcess) {
  try {
    if (key === 'start') await startProcess(row.id)
    else if (key === 'finish') await finishProcess(row.id)
    else if (key === 'skip') await skipProcess(row.id)
    else if (key === 'edit') {
      openProcess(row)
      return
    } else if (key === 'delete') {
      await deleteProcess(row.id)
    }
    ElMessage.success(t('common.message.saveSuccess'))
    void loadAll()
    emit('changed')
  } catch {
    /* http notifies */
  }
}

/* ---------------- 七维分配 ---------------- */

const assignDialog = reactive({ visible: false, id: 0 })
const assignForm = reactive({
  dimension: 'person' as TaskAssignment['dimension'],
  resourceCode: '',
  resourceName: '',
  qty: 1,
  unit: '',
  status: 'pending' as TaskAssignment['status'],
  plannedAt: '',
  remark: '',
})

function openAssign(row?: TaskAssignment) {
  assignForm.dimension = row?.dimension ?? 'person'
  assignForm.resourceCode = row?.resourceCode ?? ''
  assignForm.resourceName = row?.resourceName ?? ''
  assignForm.qty = row?.qty ?? 1
  assignForm.unit = row?.unit ?? ''
  assignForm.status = row?.status ?? 'pending'
  assignForm.plannedAt = row?.plannedAt ? row.plannedAt.slice(0, 19).replace(' ', 'T') : ''
  assignForm.remark = row?.remark ?? ''
  assignDialog.id = row?.id ?? 0
  assignDialog.visible = true
}

async function saveAssign() {
  const payload = {
    dimension: assignForm.dimension,
    resourceCode: assignForm.resourceCode,
    resourceName: assignForm.resourceName,
    qty: assignForm.qty,
    unit: assignForm.unit,
    status: assignForm.status,
    plannedAt: assignForm.plannedAt ? new Date(assignForm.plannedAt).toISOString().slice(0, 19) : undefined,
    remark: assignForm.remark,
  }
  try {
    if (assignDialog.id) await updateAssignment(assignDialog.id, payload)
    else await createAssignment(props.taskId, payload)
    ElMessage.success(t('common.message.saveSuccess'))
    assignDialog.visible = false
    void loadAll()
    emit('changed')
  } catch {
    /* http notifies */
  }
}

async function onAssignAction(key: string, row: TaskAssignment) {
  try {
    if (key === 'edit') {
      openAssign(row)
      return
    }
    if (key === 'delete') {
      await deleteAssignment(row.id)
      ElMessage.success(t('common.message.deleteSuccess'))
      void loadAll()
    emit('changed')
    }
  } catch {
    /* http notifies */
  }
}

/* ---------------- 追溯 ---------------- */

const traceDialog = reactive({ visible: false })
const traceForm = reactive({ nodeCode: 'input', nodeName: '', refNo: '', happenAt: '', remark: '' })

function openTrace() {
  traceForm.nodeCode = 'input'
  traceForm.nodeName = ''
  traceForm.refNo = ''
  traceForm.happenAt = ''
  traceForm.remark = ''
  traceDialog.visible = true
}

async function saveTrace() {
  try {
    await createTrace(props.taskId, {
      nodeCode: traceForm.nodeCode,
      nodeName: traceForm.nodeName,
      refNo: traceForm.refNo,
      happenAt: traceForm.happenAt ? new Date(traceForm.happenAt).toISOString().slice(0, 19) : undefined,
      remark: traceForm.remark,
    })
    ElMessage.success(t('common.message.saveSuccess'))
    traceDialog.visible = false
    void loadAll()
    emit('changed')
  } catch {
    /* http notifies */
  }
}

async function removeTrace(row: TaskTrace) {
  try {
    await deleteTrace(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    void loadAll()
    emit('changed')
  } catch {
    /* http notifies */
  }
}

/* ---------------- 流程图 ---------------- */

const flowNodes = computed(() => flow.value?.nodes ?? [])

/** 工序状态 → 标签色：进行中=主色，已完成=成功，跳过=中性，待开始=警告 */
function processTagType(status: string): 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  if (status === 'running') return 'primary'
  if (status === 'done') return 'success'
  if (status === 'skipped') return 'info'
  return 'warning'
}

/** 分配状态 → 标签色 */
function assignTagType(status: string): 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  if (status === 'confirmed') return 'success'
  if (status === 'allocated') return 'primary'
  if (status === 'rejected') return 'danger'
  return 'warning'
}
</script>

<template>
  <div class="task-process-panel" v-loading="loading">
    <el-tabs v-model="activeTab">
      <!-- 工序流转 -->
      <el-tab-pane name="processes">
        <template #label>
          {{ t('task.process.tabProcesses') }}
          <span v-if="processes.length" class="bs-tab-count">({{ processes.length }})</span>
        </template>
        <div class="tab-toolbar">
          <el-button v-permission="'task:process:edit'" size="small" type="primary" plain @click="openProcess()">
            {{ t('task.process.addProcess') }}
          </el-button>
          <span class="toolbar-hint">{{ t('task.process.assignHint') }}</span>
        </div>
        <el-table :data="processes" border stripe size="small">
          <el-table-column :label="t('task.process.seq')" prop="seq" width="70" sortable />
          <el-table-column :label="t('task.process.processCode')" prop="processCode" width="120" />
          <el-table-column :label="t('task.process.processName')" prop="processName" min-width="140" />
          <el-table-column :label="t('task.process.status')" width="110">
            <template #default="{ row }">
              <el-tag size="small" effect="light" round :type="processTagType(String(row.status))">
                {{ t(PROCESS_STATUS_KEYS[String(row.status)] || String(row.status)) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('task.process.plannedStart')" prop="plannedStart" width="120" />
          <el-table-column :label="t('task.process.plannedEnd')" prop="plannedEnd" width="120" />
          <el-table-column :label="t('task.process.actualStart')" prop="actualStart" width="160" />
          <el-table-column :label="t('task.process.actualEnd')" prop="actualEnd" width="160" />
          <el-table-column :label="t('task.process.operatorName')" prop="operatorName" width="110" />
          <el-table-column :label="t('task.process.deptName')" prop="deptName" width="110" />
          <el-table-column :label="t('common.action.operate')" width="130" fixed="right">
            <template #default="{ row }">
              <ActionBar :actions="processActions(row)" @select="(k) => onProcessAction(k, row)" />
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!loading && !processes.length" :description="t('task.process.flowEmpty')" />
      </el-tab-pane>

      <!-- 七维分配 -->
      <el-tab-pane name="assignments">
        <template #label>
          {{ t('task.process.tabAssignments') }}
          <span v-if="assignments.length" class="bs-tab-count">({{ assignments.length }})</span>
        </template>
        <div class="tab-toolbar">
          <el-button
            v-permission="'task:assignment:edit'"
            size="small"
            type="primary"
            plain
            @click="openAssign()"
          >
            {{ t('task.process.addAssignment') }}
          </el-button>
        </div>
        <el-table :data="assignments" border stripe size="small">
          <el-table-column :label="t('task.process.dimension')" prop="dimensionText" width="90" />
          <el-table-column :label="t('task.process.resourceName')" prop="resourceName" min-width="150" />
          <el-table-column :label="t('task.process.resourceCode')" prop="resourceCode" width="130" />
          <el-table-column :label="t('task.process.qty')" prop="qty" width="90" />
          <el-table-column :label="t('task.process.unit')" prop="unit" width="80" />
          <el-table-column :label="t('task.process.status')" width="110">
            <template #default="{ row }">
              <el-tag size="small" effect="light" round :type="assignTagType(String(row.status))">
                {{ t(ASSIGN_STATUS_KEYS[String(row.status)] || String(row.status)) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column :label="t('task.process.plannedAt')" prop="plannedAt" width="160" />
          <el-table-column :label="t('task.process.assignerName')" prop="assignerName" width="110" />
          <el-table-column :label="t('task.process.confirmedAt')" prop="confirmedAt" width="160" />
          <el-table-column :label="t('common.action.operate')" width="110" fixed="right">
            <template #default="{ row }">
              <ActionBar
                :actions="[
                  { key: 'edit', tip: 'common.action.edit', perm: 'task:assignment:edit' },
                  { key: 'delete', tip: 'common.action.delete', perm: 'task:assignment:edit', danger: true },
                ]"
                @select="(k) => onAssignAction(k, row)"
              />
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!loading && !assignments.length" :description="t('task.process.flowEmpty')" />
      </el-tab-pane>

      <!-- 全过程追溯 -->
      <el-tab-pane name="traces">
        <template #label>
          {{ t('task.process.tabTraces') }}
          <span v-if="traces.length" class="bs-tab-count">({{ traces.length }})</span>
        </template>
        <div class="tab-toolbar">
          <el-button v-permission="'task:trace:edit'" size="small" type="primary" plain @click="openTrace">
            {{ t('task.process.addTrace') }}
          </el-button>
        </div>
        <el-table :data="traces" border stripe size="small">
          <el-table-column :label="t('task.process.seq')" prop="seq" width="70" sortable />
          <el-table-column :label="t('task.process.nodeCode')" prop="nodeText" width="120" />
          <el-table-column :label="t('task.process.nodeName')" prop="nodeName" min-width="140" />
          <el-table-column :label="t('task.process.happenAt')" prop="happenAt" width="160" />
          <el-table-column :label="t('task.process.refNo')" prop="refNo" width="140" />
          <el-table-column :label="t('task.process.operator')" prop="operatorName" width="110" />
          <el-table-column :label="t('task.process.remark')" prop="remark" min-width="140" />
          <el-table-column :label="t('common.action.operate')" width="90" fixed="right">
            <template #default="{ row }">
              <ActionBar
                :actions="[{ key: 'delete', tip: 'task.process.deleteTrace', perm: 'task:trace:edit', danger: true }]"
                @select="() => removeTrace(row)"
              />
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-if="!loading && !traces.length" :description="t('task.process.flowEmpty')" />
      </el-tab-pane>

      <!-- 操作流程图 -->
      <el-tab-pane name="flow">
        <template #label>
          {{ t('task.process.tabFlow') }}
          <span v-if="flowNodes.length" class="bs-tab-count">({{ flowNodes.length }})</span>
        </template>
        <div v-if="flowNodes.length" class="flow-chain">
          <template v-for="(node, idx) in flowNodes" :key="`${node.type}-${node.code}-${idx}`">
            <div class="flow-node" :class="[`is-${node.status}`, `is-${node.type}`]">
              <div class="flow-node-title">{{ node.name || node.code }}</div>
              <div class="flow-node-meta">{{ node.statusText }}</div>
              <div v-if="node.plannedStart" class="flow-node-time">
                {{ node.plannedStart }} → {{ node.plannedEnd }}
              </div>
              <div v-else-if="node.happenAt" class="flow-node-time">{{ node.happenAt }}</div>
              <div v-if="node.operatorName" class="flow-node-time">{{ node.operatorName }}</div>
            </div>
            <div v-if="idx < flowNodes.length - 1" class="flow-arrow">→</div>
          </template>
        </div>
        <el-empty v-else :description="t('task.process.flowEmpty')" />
      </el-tab-pane>
    </el-tabs>

    <!-- 工序编辑弹窗 -->
    <el-dialog
      v-model="processDialog.visible"
      :title="processDialog.id ? t('task.process.editProcess') : t('task.process.addProcess')"
      width="var(--bs-layout-dialog-md)"
      append-to-body
    >
      <el-form :model="processForm" label-width="110px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('task.process.seq')">
              <el-input-number v-model="processForm.seq" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.process.processCode')">
              <el-select v-model="processForm.processCode" filterable style="width: 100%">
                <el-option
                  v-for="opt in processOpts.opts.value"
                  :key="String(opt.value)"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.process.processName')">
              <el-input v-model="processForm.processName" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.process.plannedStart')">
              <el-date-picker
                v-model="processForm.plannedStart"
                type="date"
                value-format="YYYY-MM-DD"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.process.plannedEnd')">
              <el-date-picker
                v-model="processForm.plannedEnd"
                type="date"
                value-format="YYYY-MM-DD"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.process.operatorName')">
              <el-input v-model="processForm.operatorName" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.process.deptName')">
              <el-input v-model="processForm.deptName" />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item :label="t('task.process.remark')">
              <el-input v-model="processForm.remark" type="textarea" :rows="2" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="processDialog.visible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="saveProcess">{{ t('common.action.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- 分配编辑弹窗 -->
    <el-dialog
      v-model="assignDialog.visible"
      :title="assignDialog.id ? t('task.process.editAssignment') : t('task.process.addAssignment')"
      width="var(--bs-layout-dialog-md)"
      append-to-body
    >
      <el-form :model="assignForm" label-width="110px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('task.process.dimension')">
              <el-select v-model="assignForm.dimension" style="width: 100%">
                <el-option
                  v-for="opt in dimensionOpts.opts.value"
                  :key="String(opt.value)"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.process.status')">
              <el-select v-model="assignForm.status" style="width: 100%">
                <el-option
                  v-for="(key, value) in ASSIGN_STATUS_KEYS"
                  :key="value"
                  :label="t(key)"
                  :value="value"
                />
              </el-select>
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.process.resourceName')">
              <el-input v-model="assignForm.resourceName" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.process.resourceCode')">
              <el-input v-model="assignForm.resourceCode" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="t('task.process.qty')">
              <el-input-number v-model="assignForm.qty" :min="0" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="t('task.process.unit')">
              <el-input v-model="assignForm.unit" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item :label="t('task.process.plannedAt')">
              <el-date-picker
                v-model="assignForm.plannedAt"
                type="datetime"
                value-format="YYYY-MM-DDTHH:mm:ss"
                style="width: 100%"
              />
            </el-form-item>
          </el-col>
          <el-col :span="24">
            <el-form-item :label="t('task.process.remark')">
              <el-input v-model="assignForm.remark" type="textarea" :rows="2" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="assignDialog.visible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="saveAssign">{{ t('common.action.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- 追溯节点弹窗 -->
    <el-dialog v-model="traceDialog.visible" :title="t('task.process.addTrace')" width="var(--bs-layout-dialog-sm)" append-to-body>
      <el-form :model="traceForm" label-width="100px">
        <el-form-item :label="t('task.process.nodeCode')">
          <el-select v-model="traceForm.nodeCode" style="width: 100%">
            <el-option v-for="n in TRACE_NODES" :key="n.value" :label="t(n.labelKey)" :value="n.value" />
          </el-select>
        </el-form-item>
        <el-form-item :label="t('task.process.nodeName')">
          <el-input v-model="traceForm.nodeName" />
        </el-form-item>
        <el-form-item :label="t('task.process.refNo')">
          <el-input v-model="traceForm.refNo" />
        </el-form-item>
        <el-form-item :label="t('task.process.happenAt')">
          <el-date-picker
            v-model="traceForm.happenAt"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item :label="t('task.process.remark')">
          <el-input v-model="traceForm.remark" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="traceDialog.visible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" @click="saveTrace">{{ t('common.action.save') }}</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.task-process-panel {
  min-width: 0;
}

.tab-toolbar {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  margin-bottom: var(--bs-space-2);
}

.toolbar-hint {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.flow-chain {
  display: flex;
  flex-wrap: wrap;
  align-items: stretch;
  gap: var(--bs-space-1);
}

.flow-node {
  min-width: 150px;
  max-width: 240px;
  padding: var(--bs-space-2);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
}

.flow-node.is-running {
  border-color: var(--bs-color-primary);
  background: var(--bs-color-brand-primary-soft);
}

.flow-node.is-done {
  border-color: var(--bs-color-semantic-success);
}

.flow-node.is-trace {
  border-style: dashed;
}

.flow-node-title {
  font-weight: 600;
  font-size: var(--bs-typography-font-size-sm);
}

.flow-node-meta {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-secondary);
}

.flow-node-time {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.flow-arrow {
  align-self: center;
  color: var(--bs-color-fg-muted);
}
</style>
