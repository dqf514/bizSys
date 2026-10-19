<script setup lang="ts">
import { computed, onActivated, onDeactivated, onUnmounted, reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import StatusTag from '@/components/common/StatusTag.vue'
import ApprovalTimeline from '@/components/approval/ApprovalTimeline.vue'
import ReportUploadDialog from '@/modules/report/components/ReportUploadDialog.vue'
import ReportDetailDrawer from '@/modules/report/components/ReportDetailDrawer.vue'
import { useContextStore, type ContextSection } from '@/stores/context'
import {
  getTask,
  deleteTask,
  taskAction,
  sampleFlow,
  addTaskItem,
  updateTaskItem,
  deleteTaskItem,
  addTaskSample,
  updateTaskSample,
  deleteTaskSample,
  type TaskAction,
} from '@/api/task'
import { listReports } from '@/api/report'
import type { Report, Task, TaskItem, TaskLog, TaskSample, TaskStatus } from '@/api/types'

defineOptions({ name: 'TaskDetailPanel' })

const props = defineProps<{
  taskId: number
}>()

const emit = defineEmits<{
  /** 任何数据变更（状态操作/条目/样品/删除）后触发，供外部刷新列表 */
  (e: 'changed'): void
  /** 任务被删除后触发，供外部关闭抽屉或返回列表 */
  (e: 'removed'): void
  /** 详情加载完成后抛出任务数据，供外部渲染标题等 */
  (e: 'loaded', task: Task): void
}>()

const { t } = useI18n()
const router = useRouter()
const context = useContextStore()

const detail = ref<Task | null>(null)
const items = ref<TaskItem[]>([])
const samples = ref<TaskSample[]>([])
const logs = ref<TaskLog[]>([])
const reports = ref<Report[]>([])
const reportsTotal = ref(0)
const reportsLoading = ref(false)
const loading = ref(false)
const activeTab = ref('basic')

const status = computed(() => detail.value?.status ?? '')
// 与后端一致：条目增改允许 assigning/assigned/in_progress（draft 走编辑页）；删除仅 draft
const canMaintainItems = computed(() => ['assigning', 'assigned', 'in_progress'].includes(status.value))
const canMaintainSamples = computed(() =>
  ['draft', 'assigning', 'assigned', 'in_progress'].includes(status.value),
)
const isDraft = computed(() => status.value === 'draft')
// 与后端一致：草稿/已驳回可进入编辑页
const canEdit = computed(() => ['draft', 'rejected'].includes(status.value))

async function loadReports() {
  if (!props.taskId) return
  reportsLoading.value = true
  try {
    const data = await listReports({ page: 1, size: 100, filters: { task_id: props.taskId } })
    reports.value = data.items ?? []
    reportsTotal.value = data.total ?? reports.value.length
  } catch {
    reports.value = []
    reportsTotal.value = 0
  } finally {
    reportsLoading.value = false
  }
}

async function load() {
  if (!props.taskId) return
  loading.value = true
  try {
    const data = await getTask(props.taskId)
    detail.value = data
    items.value = data.items ?? []
    samples.value = data.samples ?? []
    logs.value = data.logs ?? []
    emit('loaded', data)
    publishContext()
  } catch {
    detail.value = null
  } finally {
    loading.value = false
  }
  void loadReports()
}

/* ---------- 关联面板 ---------- */
function publishContext() {
  const d = detail.value
  if (!d) return
  const sections: ContextSection[] = []
  if (d.contractId) {
    sections.push({
      key: 'contract',
      title: 'common.context.relatedContract',
      type: 'links',
      items: [{ label: d.contractNo || String(d.contractId), to: `/contract/contracts/${d.contractId}` }],
    })
  }
  sections.push({
    key: 'customer',
    title: 'common.context.customer',
    type: 'fields',
    items: [{ label: 'task.task.customerName', value: d.customerName || '-' }],
  })
  const needReport = items.value.filter((i) => i.needReport).length
  const sealed = items.value.filter((i) => i.reportStatus === 'sealed').length
  const uploadedNotSealed = items.value.filter((i) => i.reportStatus && i.reportStatus !== 'sealed').length
  sections.push({
    key: 'reportProgress',
    title: 'common.context.reportProgress',
    type: 'stats',
    items: [
      { label: 'common.context.needReport', value: needReport },
      { label: 'common.context.sealed', value: sealed },
      { label: 'common.context.pendingSeal', value: uploadedNotSealed, emphasize: uploadedNotSealed > 0 },
    ],
  })
  context.publish({ title: d.taskName, subtitle: d.taskNo, recordKey: `task:${d.id}`, sections })
}

// used both as a routed page (keep-alive) and inside the TaskList quick-view drawer:
// re-publish when re-activated, clear when deactivated or unmounted (drawer close)
onActivated(() => {
  if (detail.value) publishContext()
})
onDeactivated(() => context.clear())
onUnmounted(() => context.clear())

watch(
  () => props.taskId,
  () => {
    activeTab.value = 'basic'
    void load()
  },
  { immediate: true },
)

/* ---------- 状态机操作（自 TaskList 迁移） ---------- */
const actionLoading = ref(false)

function availableActions(s: TaskStatus | ''): { action: TaskAction; labelKey: string; type: string }[] {
  const map: Record<string, { action: TaskAction; labelKey: string; type: string }[]> = {
    draft: [{ action: 'submit', labelKey: 'task.task.submit', type: 'warning' }],
    rejected: [{ action: 'submit', labelKey: 'task.task.submit', type: 'warning' }],
    assigning: [{ action: 'start', labelKey: 'task.task.start', type: 'primary' }],
    assigned: [{ action: 'start', labelKey: 'task.task.start', type: 'primary' }],
    in_progress: [{ action: 'finish', labelKey: 'task.task.finish', type: 'success' }],
    finished: [{ action: 'close', labelKey: 'task.task.close', type: 'info' }],
  }
  const actions = [...(map[s] ?? [])]
  // any non-terminal status can be stopped
  if (s && s !== 'closed' && s !== 'stopped') {
    actions.push({ action: 'stop', labelKey: 'task.task.stop', type: 'danger' })
  }
  return actions
}

async function doAction(action: TaskAction) {
  if (!detail.value) return
  const confirmMap: Record<string, string> = {
    submit: t('task.task.submitConfirm'),
    stop: t('task.task.stopConfirm'),
    close: t('task.task.closeConfirm'),
    finish: t('task.task.finishConfirm'),
    start: '',
  }
  const msg = confirmMap[action]
  if (msg) {
    try {
      await ElMessageBox.confirm(msg, t('common.action.confirm'), { type: 'warning' })
    } catch {
      return
    }
  }
  actionLoading.value = true
  try {
    await taskAction(detail.value.id, action)
    ElMessage.success(t('common.message.submitSuccess'))
    await load()
    emit('changed')
  } catch {
    /* http notifies */
  } finally {
    actionLoading.value = false
  }
}

function openEdit() {
  if (!detail.value) return
  router.push(`/task/tasks/${detail.value.id}/edit`)
}

function gotoFlowCenter() {
  router.push('/approval')
}

async function removeTask() {
  if (!detail.value) return
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteTask(detail.value.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    emit('changed')
    emit('removed')
  } catch {
    /* http notifies */
  }
}

async function doSampleFlow(row: TaskSample, action: 'in' | 'out') {
  if (!row.id) return
  const msg = action === 'in' ? t('task.task.inConfirm') : t('task.task.outConfirm')
  try {
    await ElMessageBox.confirm(msg, t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await sampleFlow(row.id, action)
    row.inStock = action === 'in' ? 'in' : 'out'
    ElMessage.success(t('common.message.submitSuccess'))
    void load()
    emit('changed')
  } catch {
    /* http notifies */
  }
}

/* ---------- 条目维护 ---------- */
const itemVisible = ref(false)
const itemSaving = ref(false)
const itemFormRef = ref<FormInstance>()
const editingItemId = ref<number | null>(null)
const itemForm = reactive({
  itemCode: '',
  name: '',
  std: '',
  dept: '',
  inspector: '',
  qty: 1 as number,
  settleType: '',
  needReport: false,
})

function openItemCreate() {
  editingItemId.value = null
  Object.assign(itemForm, {
    itemCode: '',
    name: '',
    std: '',
    dept: '',
    inspector: '',
    qty: 1,
    settleType: '',
    needReport: false,
  })
  itemVisible.value = true
}

function openItemEdit(row: TaskItem) {
  editingItemId.value = row.id ?? null
  Object.assign(itemForm, {
    itemCode: row.itemCode ?? '',
    name: row.name ?? '',
    std: row.std ?? '',
    dept: row.dept ?? '',
    inspector: row.inspector ?? '',
    qty: Number(row.qty) || 0,
    settleType: row.settleType ?? '',
    needReport: Boolean(row.needReport),
  })
  itemVisible.value = true
}

async function saveItem() {
  if (!itemFormRef.value) return
  const ok = await itemFormRef.value.validate().catch(() => false)
  if (!ok) return
  itemSaving.value = true
  try {
    const payload = {
      itemCode: itemForm.itemCode,
      name: itemForm.name,
      std: itemForm.std,
      dept: itemForm.dept,
      inspector: itemForm.inspector,
      qty: Number(itemForm.qty) || 0,
      settleType: itemForm.settleType,
      needReport: itemForm.needReport ? 1 : 0,
    }
    if (editingItemId.value) await updateTaskItem(editingItemId.value, payload as never)
    else await addTaskItem(props.taskId, payload as never)
    ElMessage.success(t('common.message.saveSuccess'))
    itemVisible.value = false
    void load()
    emit('changed')
  } catch {
    /* http notifies */
  } finally {
    itemSaving.value = false
  }
}

async function removeItem(row: TaskItem) {
  if (!row.id) return
  try {
    await ElMessageBox.confirm(t('task.task.deleteItemConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteTaskItem(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    void load()
    emit('changed')
  } catch {
    /* http notifies */
  }
}

/* ---------- 样品维护 ---------- */
const sampleVisible = ref(false)
const sampleSaving = ref(false)
const sampleFormRef = ref<FormInstance>()
const editingSampleId = ref<number | null>(null)
const sampleForm = reactive({
  name: '',
  model: '',
  vin: '',
  vehicleType: '',
  sampleDate: '',
  inStock: 'in' as 'in' | 'out',
})

function openSampleCreate() {
  editingSampleId.value = null
  Object.assign(sampleForm, { name: '', model: '', vin: '', vehicleType: '', sampleDate: '', inStock: 'in' })
  sampleVisible.value = true
}

function openSampleEdit(row: TaskSample) {
  editingSampleId.value = row.id ?? null
  Object.assign(sampleForm, {
    name: row.name ?? '',
    model: row.model ?? '',
    vin: row.vin ?? '',
    vehicleType: row.vehicleType ?? '',
    sampleDate: row.sampleDate ?? '',
    inStock: row.inStock === 'out' ? 'out' : 'in',
  })
  sampleVisible.value = true
}

async function saveSample() {
  if (!sampleFormRef.value) return
  const ok = await sampleFormRef.value.validate().catch(() => false)
  if (!ok) return
  sampleSaving.value = true
  try {
    const payload = {
      name: sampleForm.name,
      model: sampleForm.model,
      vin: sampleForm.vin,
      vehicleType: sampleForm.vehicleType,
      sampleDate: sampleForm.sampleDate || undefined,
      inStock: sampleForm.inStock,
    }
    if (editingSampleId.value) await updateTaskSample(editingSampleId.value, payload as never)
    else await addTaskSample(props.taskId, payload as never)
    ElMessage.success(t('common.message.saveSuccess'))
    sampleVisible.value = false
    void load()
    emit('changed')
  } catch {
    /* http notifies */
  } finally {
    sampleSaving.value = false
  }
}

async function removeSample(row: TaskSample) {
  if (!row.id) return
  try {
    await ElMessageBox.confirm(t('task.task.deleteSampleConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteTaskSample(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    void load()
    emit('changed')
  } catch {
    /* http notifies */
  }
}

/* ---------- 报告（只读列表 + 上传入口） ---------- */
const reportUploadVisible = ref(false)
const reportDetailVisible = ref(false)
const reportDetailId = ref<number | null>(null)

function openReportDetail(row: Report) {
  reportDetailId.value = row.id
  reportDetailVisible.value = true
}

function onReportUploaded() {
  void loadReports()
  void load()
  emit('changed')
}

function logActionLabel(action: string) {
  if (action === 'in') return t('task.task.logActionIn')
  if (action === 'out') return t('task.task.logActionOut')
  return action || '-'
}
</script>

<template>
  <div class="task-detail-panel" v-loading="loading">
    <div v-if="detail" class="panel-toolbar">
      <StatusTag :status="detail.status" i18n-prefix="task.task.status" />
      <div class="panel-actions">
        <el-button
          v-for="a in availableActions(detail.status)"
          :key="a.action"
          v-permission="a.action === 'submit' ? 'task:assign' : 'task:edit'"
          size="small"
          :type="a.type as any"
          :loading="actionLoading"
          @click="doAction(a.action)"
        >
          {{ t(a.labelKey) }}
        </el-button>
        <el-button v-if="canEdit" v-permission="'task:edit'" size="small" @click="openEdit">
          {{ t('common.action.edit') }}
        </el-button>
        <el-button v-if="isDraft" v-permission="'task:edit'" size="small" type="danger" plain @click="removeTask">
          {{ t('common.action.delete') }}
        </el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab">
      <el-tab-pane :label="t('task.task.tabBasic')" name="basic">
        <el-descriptions v-if="detail" :column="2" border>
          <el-descriptions-item :label="t('task.task.taskNo')">{{ detail.taskNo }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.taskName')">{{ detail.taskName }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.taskType')">{{ detail.taskTypeLabel || detail.taskType }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.customerName')">{{ detail.customerName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.contractNo')">{{ detail.contractNo || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.bizBlock')">{{ detail.bizBlockLabel || detail.bizBlock || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.deptName')">{{ detail.deptName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.ownerName')">{{ detail.ownerName || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.receiver')">{{ detail.receiver || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.receiverUnit')">{{ detail.receiverUnit || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.planFinishDate')">{{ detail.planFinishDate || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.partySystem')">{{ detail.partySystem || '-' }}</el-descriptions-item>
          <el-descriptions-item :label="t('task.task.content')" :span="2">{{ detail.content || '-' }}</el-descriptions-item>
        </el-descriptions>
      </el-tab-pane>

      <el-tab-pane name="items">
        <template #label>
          {{ t('task.task.tabItems') }}
          <span v-if="items.length" class="bs-tab-count">({{ items.length }})</span>
        </template>
        <div v-if="canMaintainItems" class="tab-toolbar">
          <el-button v-permission="'task:edit'" size="small" type="primary" plain @click="openItemCreate">
            {{ t('task.task.addItem') }}
          </el-button>
        </div>
        <el-table :data="items" border stripe size="small">
          <el-table-column :label="t('task.task.itemCode')" prop="itemCode" width="120" />
          <el-table-column :label="t('task.task.itemName')" prop="name" min-width="140" />
          <el-table-column :label="t('task.task.itemStd')" prop="std" min-width="110" />
          <el-table-column :label="t('task.task.itemDept')" prop="dept" width="110" />
          <el-table-column :label="t('task.task.itemInspector')" prop="inspector" width="100" />
          <el-table-column :label="t('task.task.itemQty')" prop="qty" width="80" />
          <el-table-column :label="t('task.task.itemReportNo')" prop="reportNo" width="130" />
          <el-table-column :label="t('task.task.itemReportStatus')" width="120">
            <template #default="{ row }">
              <StatusTag
                v-if="row.reportStatus"
                :status="String(row.reportStatus)"
                i18n-prefix="report.report.status"
              />
              <span v-else>-</span>
            </template>
          </el-table-column>
          <el-table-column
            v-if="canMaintainItems || isDraft"
            :label="t('common.action.operate')"
            width="130"
            fixed="right"
          >
            <template #default="{ row }">
              <el-button
                v-if="canMaintainItems"
                v-permission="'task:edit'"
                link
                type="primary"
                @click="openItemEdit(row as unknown as TaskItem)"
              >
                {{ t('common.action.edit') }}
              </el-button>
              <el-button
                v-if="isDraft"
                v-permission="'task:edit'"
                link
                type="danger"
                @click="removeItem(row as unknown as TaskItem)"
              >
                {{ t('common.action.delete') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane name="samples">
        <template #label>
          {{ t('task.task.tabSamples') }}
          <span v-if="samples.length" class="bs-tab-count">({{ samples.length }})</span>
        </template>
        <div v-if="canMaintainSamples" class="tab-toolbar">
          <el-button v-permission="'task:edit'" size="small" type="primary" plain @click="openSampleCreate">
            {{ t('task.task.registerSample') }}
          </el-button>
        </div>
        <el-table :data="samples" border stripe size="small">
          <el-table-column :label="t('task.task.sampleNo')" prop="sampleNo" width="130" />
          <el-table-column :label="t('task.task.sampleName')" prop="name" min-width="130" />
          <el-table-column :label="t('task.task.sampleModel')" prop="model" width="110" />
          <el-table-column :label="t('task.task.sampleVin')" prop="vin" width="140" />
          <el-table-column :label="t('task.task.sampleVehicleType')" prop="vehicleType" width="110" />
          <el-table-column :label="t('task.task.sampleDate')" prop="sampleDate" width="110" />
          <el-table-column :label="t('task.task.sampleInStock')" width="90">
            <template #default="{ row }">
              <StatusTag :status="String(row.inStock)" i18n-prefix="task.task.sampleStatus" />
            </template>
          </el-table-column>
          <el-table-column :label="t('common.action.operate')" width="220" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.inStock !== 'in'"
                link
                type="success"
                @click="doSampleFlow(row as unknown as TaskSample, 'in')"
              >
                {{ t('task.task.sampleIn') }}
              </el-button>
              <el-button
                v-if="row.inStock === 'in'"
                link
                type="warning"
                @click="doSampleFlow(row as unknown as TaskSample, 'out')"
              >
                {{ t('task.task.sampleOut') }}
              </el-button>
              <el-button
                v-if="canMaintainSamples"
                v-permission="'task:edit'"
                link
                type="primary"
                @click="openSampleEdit(row as unknown as TaskSample)"
              >
                {{ t('common.action.edit') }}
              </el-button>
              <el-button
                v-if="isDraft"
                v-permission="'task:edit'"
                link
                type="danger"
                @click="removeSample(row as unknown as TaskSample)"
              >
                {{ t('common.action.delete') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane name="reports">
        <template #label>
          {{ t('task.task.tabReports') }}
          <span v-if="reportsTotal" class="bs-tab-count">({{ reportsTotal }})</span>
        </template>
        <div class="tab-toolbar">
          <el-button v-permission="'report:create'" size="small" type="primary" plain @click="reportUploadVisible = true">
            {{ t('report.report.upload') }}
          </el-button>
        </div>
        <el-table v-loading="reportsLoading" :data="reports" border stripe size="small">
          <el-table-column :label="t('report.report.reportNo')" prop="reportNo" width="150" />
          <el-table-column :label="t('report.report.itemName')" prop="itemName" min-width="140" />
          <el-table-column :label="t('report.report.fileName')" prop="fileName" min-width="160" />
          <el-table-column :label="t('common.form.status')" width="110">
            <template #default="{ row }">
              <StatusTag :status="String(row.status)" i18n-prefix="report.report.status" />
            </template>
          </el-table-column>
          <el-table-column :label="t('report.report.createTime')" prop="createTime" width="160" />
          <el-table-column :label="t('common.action.operate')" width="90" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" @click="openReportDetail(row as unknown as Report)">
                {{ t('common.action.detail') }}
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane name="logs">
        <template #label>
          {{ t('task.task.tabLogs') }}
          <span v-if="logs.length" class="bs-tab-count">({{ logs.length }})</span>
        </template>
        <el-table :data="logs" border stripe size="small">
          <el-table-column :label="t('task.task.logSampleNo')" prop="sampleNo" width="150" />
          <el-table-column :label="t('task.task.logAction')" width="100">
            <template #default="{ row }">{{ logActionLabel(String(row.action)) }}</template>
          </el-table-column>
          <el-table-column :label="t('task.task.logOperator')" prop="operatorName" width="120" />
          <el-table-column :label="t('task.task.logTime')" prop="createTime" width="160" />
          <el-table-column :label="t('task.task.logRemark')" prop="remark" min-width="180" />
        </el-table>
      </el-tab-pane>

      <el-tab-pane v-if="detail?.flow" :label="t('task.task.tabFlow')" name="flow">
        <div class="tab-toolbar">
          <el-button size="small" type="primary" plain @click="gotoFlowCenter">
            {{ t('task.task.flowGoto') }}
          </el-button>
        </div>
        <el-descriptions :column="2" border size="small" class="flow-summary">
          <el-descriptions-item :label="t('task.task.flowDefinition')">
            {{ detail.flow.definitionCode || '-' }}
          </el-descriptions-item>
          <el-descriptions-item :label="t('task.task.flowStatus')">
            <StatusTag :status="String(detail.flow.status)" i18n-prefix="approval.approval.status" />
          </el-descriptions-item>
        </el-descriptions>
        <ApprovalTimeline :records="detail.flow.timeline ?? []" />
      </el-tab-pane>
    </el-tabs>

    <!-- 条目维护弹窗 -->
    <el-dialog
      v-model="itemVisible"
      :title="editingItemId ? t('task.task.editItem') : t('task.task.addItem')"
      width="640px"
      append-to-body
    >
      <el-form ref="itemFormRef" :model="itemForm" label-width="110px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item :label="t('task.task.itemCode')" prop="itemCode">
              <el-input v-model="itemForm.itemCode" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item
              :label="t('task.task.itemName')"
              prop="name"
              :rules="[{ required: true, message: t('common.form.required') }]"
            >
              <el-input v-model="itemForm.name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.task.itemStd')" prop="std">
              <el-input v-model="itemForm.std" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.task.itemDept')" prop="dept">
              <el-input v-model="itemForm.dept" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.task.itemInspector')" prop="inspector">
              <el-input v-model="itemForm.inspector" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.task.itemQty')" prop="qty">
              <el-input v-model="itemForm.qty" :min="0" controls-position="right" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.task.itemSettleType')" prop="settleType">
              <el-input v-model="itemForm.settleType" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.task.itemNeedReport')" prop="needReport">
              <el-switch v-model="itemForm.needReport" />
              <div class="form-tip">{{ t('task.task.needReportTip') }}</div>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="itemVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="itemSaving" @click="saveItem">{{ t('common.action.save') }}</el-button>
      </template>
    </el-dialog>

    <!-- 样品维护弹窗 -->
    <el-dialog
      v-model="sampleVisible"
      :title="editingSampleId ? t('task.task.editSample') : t('task.task.registerSample')"
      width="640px"
      append-to-body
    >
      <el-form ref="sampleFormRef" :model="sampleForm" label-width="110px">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item
              :label="t('task.task.sampleName')"
              prop="name"
              :rules="[{ required: true, message: t('common.form.required') }]"
            >
              <el-input v-model="sampleForm.name" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.task.sampleModel')" prop="model">
              <el-input v-model="sampleForm.model" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.task.sampleVin')" prop="vin">
              <el-input v-model="sampleForm.vin" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.task.sampleVehicleType')" prop="vehicleType">
              <el-input v-model="sampleForm.vehicleType" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.task.sampleDate')" prop="sampleDate">
              <el-date-picker v-model="sampleForm.sampleDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item :label="t('task.task.sampleInStock')" prop="inStock">
              <el-radio-group v-model="sampleForm.inStock">
                <el-radio value="in">{{ t('task.task.sampleStatusIn') }}</el-radio>
                <el-radio value="out">{{ t('task.task.sampleStatusOut') }}</el-radio>
              </el-radio-group>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
      <template #footer>
        <el-button @click="sampleVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="sampleSaving" @click="saveSample">{{ t('common.action.save') }}</el-button>
      </template>
    </el-dialog>
    <!-- 报告上传 / 详情 -->
    <ReportUploadDialog v-model="reportUploadVisible" :task-id="taskId" @uploaded="onReportUploaded" />
    <ReportDetailDrawer v-model="reportDetailVisible" :report-id="reportDetailId" />
  </div>
</template>

<style scoped>
.task-detail-panel {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
  min-height: 0;
}

.panel-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bs-space-2);
}

.panel-actions {
  display: flex;
  align-items: center;
  gap: var(--bs-space-1);
  flex-wrap: wrap;
}

.tab-toolbar {
  display: flex;
  justify-content: flex-end;
  margin-bottom: var(--bs-space-2);
}

.flow-summary {
  margin-bottom: var(--bs-space-3);
}

.form-tip {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  line-height: 1.4;
}
</style>
