<script setup lang="ts">
/**
 * 项目管理（B5 CSV 31）。
 *
 * 项目全生命周期：立项（可直接新建或基于已审批合同）→ 策划 → 执行 → 验收 → 结项；
 * 甘特行由「任务输入 + 已发布排期」自动生成，也可手工维护里程碑。
 */
import { defineAsyncComponent, onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import BackButton from '@/components/common/BackButton.vue'
import CustomerSelect from '@/components/form/CustomerSelect.vue'
import ContractSelect from '@/components/form/ContractSelect.vue'
import { useListPage } from '@/composables/useListPage'
import { useFlowCapability } from '@/composables/useFlowCapability'
import {
  createProject,
  createProjectFromContract,
  createProjectTask,
  deleteProject,
  deleteProjectTask,
  exportProjects,
  generateProjectTasks,
  getProject,
  listProjects,
  projectCounts,
  submitProject,
  updateProject,
  updateProjectTask,
} from '@/api/project'
import type { Project, ProjectTask } from '@/api/types'

// echarts 体积较大，甘特组件按需异步加载
// eslint-disable-next-line @typescript-eslint/no-unused-vars -- template 中作为组件使用
const ProjectGantt = defineAsyncComponent(() => import('../components/ProjectGantt.vue'))

defineOptions({ name: 'ProjectList' })

const { t } = useI18n()
/** F5：立项审批流程开关（关闭时只存草稿，由列表页人工处理） */
const { flowEnabled } = useFlowCapability()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'project.name', placeholderKey: 'project.name', width: 220 },
]

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'draft', labelKey: 'project.status.draft', count: 0 },
  { value: 'approving', labelKey: 'project.status.approving', count: 0 },
  { value: 'planning', labelKey: 'project.status.planning', count: 0 },
  { value: 'executing', labelKey: 'project.status.executing', count: 0 },
  { value: 'accepting', labelKey: 'project.status.accepting', count: 0 },
  { value: 'closed', labelKey: 'project.status.closed', count: 0 },
  { value: 'cancelled', labelKey: 'project.status.cancelled', count: 0 },
  { value: 'rejected', labelKey: 'project.status.rejected', count: 0 },
])

const list = useListPage<Project>({
  fetch: async (params) => {
    const data = await listProjects({ ...params, q: searchModel.value.q || undefined })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) => exportProjects({ ...params, q: searchModel.value.q || undefined }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

async function loadCounts() {
  try {
    const counts = (await projectCounts()) ?? {}
    let all = 0
    for (const tab of statusTabs.value) {
      if (tab.value === 'all') continue
      tab.count = counts[tab.value] ?? 0
      all += tab.count
    }
    const allTab = statusTabs.value.find((x) => x.value === 'all')
    if (allTab) allTab.count = all
  } catch {
    /* counts optional */
  }
}

onMounted(() => void loadCounts())

const columns: ListColumn[] = [
  { prop: 'projectNo', labelKey: 'project.projectNo', width: 150, sortable: 'project_no' },
  { prop: 'name', labelKey: 'project.name', minWidth: 180 },
  { prop: 'customerName', labelKey: 'project.customerName', width: 150 },
  { prop: 'contractNo', labelKey: 'project.contractNo', width: 150 },
  { prop: 'managerName', labelKey: 'project.managerName', width: 110 },
  { prop: 'startDate', labelKey: 'project.startDate', width: 120, sortable: 'start_date' },
  { prop: 'endDate', labelKey: 'project.endDate', width: 120, sortable: 'end_date' },
  { prop: 'progress', labelKey: 'project.progress', width: 90, align: 'right', sortable: 'progress' },
  { prop: 'taskCount', labelKey: 'project.taskCount', width: 90, align: 'right' },
  { prop: 'statusText', labelKey: 'project.status.draft', width: 100 },
  { prop: 'createTime', labelKey: 'common.form.createTime', width: 160, sortable: 'create_time' },
]

function projectTagType(status: string): 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  if (status === 'executing') return 'primary'
  if (status === 'closed') return 'success'
  if (status === 'cancelled') return 'info'
  if (status === 'accepting') return 'warning'
  return 'info'
}

/* ---------------- 新建 / 编辑项目 ---------------- */

const formDialog = reactive({ visible: false, loading: false, id: 0, fromContract: false })
const form = reactive({
  name: '',
  customerId: null as number | null,
  customerName: '',
  contractId: null as number | null,
  contractNo: '',
  managerName: '',
  deptName: '',
  startDate: '',
  endDate: '',
  budgetAmount: 0,
  description: '',
  remark: '',
  status: 'draft' as Project['status'],
})

function resetForm() {
  form.name = ''
  form.customerId = null
  form.customerName = ''
  form.contractId = null
  form.contractNo = ''
  form.managerName = ''
  form.deptName = ''
  form.startDate = ''
  form.endDate = ''
  form.budgetAmount = 0
  form.description = ''
  form.remark = ''
  form.status = 'draft'
}

function openCreate(fromContract: boolean) {
  resetForm()
  formDialog.id = 0
  formDialog.fromContract = fromContract
  formDialog.visible = true
}

function openEdit(row: Project) {
  resetForm()
  formDialog.id = row.id
  formDialog.fromContract = false
  form.name = row.name
  form.customerId = row.customerId
  form.customerName = row.customerName
  form.contractId = row.contractId
  form.contractNo = row.contractNo
  form.managerName = row.managerName
  form.deptName = row.deptName
  form.startDate = row.startDate
  form.endDate = row.endDate
  form.budgetAmount = row.budgetAmount
  form.description = row.description
  form.remark = row.remark
  form.status = row.status
  formDialog.visible = true
}

function onContractChange(v: number | string | null, opt?: { customerId?: number | null; customerName?: string; label?: string }) {
  form.contractId = v ? Number(v) : null
  form.contractNo = opt?.label ?? form.contractNo
  if (opt?.customerId) form.customerId = opt.customerId
  if (opt?.customerName) form.customerName = opt.customerName
}

function onCustomerChange(v: number | string | null, opt?: { label?: string }) {
  form.customerId = v ? Number(v) : null
  form.customerName = opt?.label ?? form.customerName
}

/** 保存：submit=false 只存草稿；submit=true 保存后立即提交立项审批（进入审批中） */
async function saveProject(submit = false) {
  if (!form.name.trim()) {
    ElMessage.warning(t('common.form.required'))
    return
  }
  formDialog.loading = true
  const payload = {
    name: form.name,
    customerId: form.customerId,
    customerName: form.customerName,
    contractId: form.contractId,
    contractNo: form.contractNo,
    managerName: form.managerName,
    deptName: form.deptName,
    startDate: form.startDate || undefined,
    endDate: form.endDate || undefined,
    budgetAmount: form.budgetAmount,
    description: form.description,
    remark: form.remark,
    status: formDialog.id ? form.status : 'draft',
  }
  try {
    let savedId = formDialog.id
    if (formDialog.id) {
      await updateProject(formDialog.id, payload)
    } else if (formDialog.fromContract) {
      savedId = (await createProjectFromContract(payload))?.id
    } else {
      savedId = (await createProject(payload))?.id
    }
    ElMessage.success(t('common.message.saveSuccess'))
    if (submit && savedId) {
      await submitProject(savedId)
      ElMessage.success(t('common.message.submitSuccess'))
    }
    formDialog.visible = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    formDialog.loading = false
  }
}

/* ---------------- 项目详情 ---------------- */

const detail = reactive({ visible: false, loading: false, project: null as Project | null })
const ganttItems = ref<ProjectTask[]>([])
const activeDetailTab = ref('gantt')

async function openDetail(row: Project) {
  detail.visible = true
  detail.loading = true
  activeDetailTab.value = 'gantt'
  try {
    const p = await getProject(row.id)
    detail.project = p
    ganttItems.value = p.gantt?.items ?? []
  } catch {
    detail.project = null
    ganttItems.value = []
  } finally {
    detail.loading = false
  }
}

function projectActions(row: Project): ActionItem[] {
  const actions: ActionItem[] = [{ key: 'detail', tip: 'project.detail' }]
  // F5：立项须经审批，提交后进入审批中，审批通过才进入策划阶段
  if (row.status === 'draft' || row.status === 'rejected') {
    actions.push({ key: 'submit', tip: 'project.submitApproval', perm: 'project:submit' })
  }
  actions.push({ key: 'edit', tip: 'common.action.edit', perm: 'project:edit' })
  if (row.status === 'draft' || row.status === 'cancelled') {
    actions.push({ key: 'delete', tip: 'common.action.delete', perm: 'project:delete', danger: true })
  }
  return actions
}

async function onProjectAction(key: string, row: Project) {
  try {
    if (key === 'detail') {
      openDetail(row)
      return
    }
    if (key === 'submit') {
      await submitProject(row.id)
      ElMessage.success(t('common.message.submitSuccess'))
      list.refresh()
      return
    }
    if (key === 'edit') {
      openEdit(row)
      return
    }
    if (key === 'delete') {
      await deleteProject(row.id)
      ElMessage.success(t('common.message.deleteSuccess'))
      list.refresh()
    }
  } catch {
    /* http notifies */
  }
}

/* ---------------- 甘特生成与维护 ---------------- */

const generateDialog = reactive({ visible: false, loading: false })
const generateForm = reactive({ groupCode: '', overwrite: false })

function openGenerate() {
  generateForm.groupCode = ''
  generateForm.overwrite = false
  generateDialog.visible = true
}

async function runGenerate() {
  const p = detail.project
  if (!p) return
  generateDialog.loading = true
  try {
    const gantt = await generateProjectTasks(p.id, {
      groupCode: generateForm.groupCode || undefined,
      overwrite: generateForm.overwrite,
    })
    ganttItems.value = gantt.items ?? []
    ElMessage.success(t('project.generated', { count: gantt.created ?? ganttItems.value.length }))
    generateDialog.visible = false
  } catch {
    /* http notifies */
  } finally {
    generateDialog.loading = false
  }
}

const rowDialog = reactive({ visible: false, loading: false, id: 0 })
const rowForm = reactive({
  taskName: '',
  seq: 0,
  groupCode: '',
  ownerName: '',
  startDate: '',
  endDate: '',
  progress: 0,
  milestone: false,
  weight: 1,
  status: 'pending' as ProjectTask['status'],
  remark: '',
})

function openRow(item?: ProjectTask) {
  rowForm.taskName = item?.taskName ?? ''
  rowForm.seq = item?.seq ?? ganttItems.value.length
  rowForm.groupCode = item?.groupCode ?? ''
  rowForm.ownerName = item?.ownerName ?? ''
  rowForm.startDate = item?.startDate ?? ''
  rowForm.endDate = item?.endDate ?? ''
  rowForm.progress = item?.progress ?? 0
  rowForm.milestone = item?.milestone ?? false
  rowForm.weight = item?.weight ?? 1
  rowForm.status = item?.status ?? 'pending'
  rowForm.remark = item?.remark ?? ''
  rowDialog.id = item?.id ?? 0
  rowDialog.visible = true
}

async function saveRow() {
  const p = detail.project
  if (!p) return
  if (!rowForm.taskName.trim()) {
    ElMessage.warning(t('common.form.required'))
    return
  }
  rowDialog.loading = true
  try {
    const gantt = rowDialog.id
      ? await updateProjectTask(rowDialog.id, {
          taskName: rowForm.taskName,
          seq: rowForm.seq,
          groupCode: rowForm.groupCode,
          ownerName: rowForm.ownerName,
          startDate: rowForm.startDate || undefined,
          endDate: rowForm.endDate || undefined,
          progress: rowForm.progress,
          milestone: rowForm.milestone,
          weight: rowForm.weight,
          status: rowForm.status,
          remark: rowForm.remark,
        })
      : await createProjectTask(p.id, {
          taskName: rowForm.taskName,
          seq: rowForm.seq,
          groupCode: rowForm.groupCode,
          ownerName: rowForm.ownerName,
          startDate: rowForm.startDate || undefined,
          endDate: rowForm.endDate || undefined,
          progress: rowForm.progress,
          milestone: rowForm.milestone,
          weight: rowForm.weight,
          status: rowForm.status,
          remark: rowForm.remark,
        })
    ganttItems.value = gantt.items ?? []
    ElMessage.success(t('common.message.saveSuccess'))
    rowDialog.visible = false
  } catch {
    /* http notifies */
  } finally {
    rowDialog.loading = false
  }
}

async function removeRow(item: ProjectTask) {
  try {
    await deleteProjectTask(item.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    if (detail.project) await openDetail(detail.project)
  } catch {
    /* http notifies */
  }
}

const ROW_STATUS = [
  { value: 'pending', labelKey: 'project.status.pending' },
  { value: 'doing', labelKey: 'project.status.doing' },
  { value: 'done', labelKey: 'project.status.done' },
  { value: 'delayed', labelKey: 'project.status.delayed' },
]

const GROUP_OPTIONS = [
  { value: '', labelKey: 'project.groupCode' },
  { value: 'sim', labelKey: 'project.group.sim' },
  { value: 'model', labelKey: 'project.group.model' },
  { value: 'test', labelKey: 'project.group.test' },
  { value: 'outsource', labelKey: 'project.group.outsource' },
]
</script>

<template>
  <ListPage :title="t('project.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'project:create'" type="primary" size="small" @click="openCreate(false)">
        {{ t('project.create') }}
      </el-button>
      <el-button v-permission="'project:create'" size="small" @click="openCreate(true)">
        {{ t('project.fromContract') }}
      </el-button>
      <ExportButton v-permission="'project:list:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar v-model="searchModel" :fields="searchFields" @search="list.search" @reset="list.reset" />
    </template>

    <template #statusTabs>
      <StatusTabs
        :tabs="statusTabs"
        :model-value="String(list.query.status)"
        @update:model-value="list.setStatus"
      />
    </template>

    <template #table>
      <ListTable
        :columns="columns"
        :data="list.items.value as unknown as Record<string, unknown>[]"
        :loading="list.loading.value"
        :total="list.total.value"
        :page="Number(list.query.page)"
        :size="Number(list.query.size)"
        row-key="id"
        @update:page="list.setPage"
        @update:size="list.setSize"
        @sort-change="list.onSortChange"
      >
        <template #statusText="{ row }">
          <el-tag size="small" effect="light" round :type="projectTagType(String(row.status))">
            {{ row.statusText || row.status }}
          </el-tag>
        </template>
        <template #projectNo="{ row }">
          <el-button link type="primary" @click="openDetail(row as unknown as Project)">
            {{ row.projectNo || '-' }}
          </el-button>
        </template>
        <template #extraColumns>
          <el-table-column
            :label="t('common.action.operate')"
            width="90"
            fixed="right"
            align="center"
            header-align="center"
          >
            <template #default="{ row }">
              <ActionBar :actions="projectActions(row)" @select="(k) => onProjectAction(k, row as unknown as Project)" />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <!-- 项目详情抽屉 -->
  <el-drawer
    v-model="detail.visible"
    :title="detail.project ? `${detail.project.projectNo} · ${detail.project.name}` : t('project.detail')"
    size="var(--bs-layout-drawer-xl)"
    append-to-body
  >
    <div v-loading="detail.loading" class="project-detail">
      <div class="detail-head">
        <BackButton @click="detail.visible = false" />
        <div class="detail-head-actions">
          <el-button
            v-permission="'project:edit'"
            size="small"
            type="primary"
            plain
            @click="openGenerate"
          >
            {{ t('project.generateGantt') }}
          </el-button>
          <el-button v-permission="'project:edit'" size="small" @click="openRow()">
            {{ t('project.addTask') }}
          </el-button>
        </div>
      </div>

      <el-descriptions v-if="detail.project" :column="3" border size="small">
        <el-descriptions-item :label="t('project.customerName')">
          {{ detail.project.customerName || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('project.contractNo')">
          {{ detail.project.contractNo || t('project.noContract') }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('project.managerName')">
          {{ detail.project.managerName || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('project.startDate')">
          {{ detail.project.startDate || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('project.endDate')">
          {{ detail.project.endDate || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('project.progress')">
          {{ detail.project.progress }}%
        </el-descriptions-item>
        <el-descriptions-item :label="t('project.budgetAmount')">
          {{ detail.project.budgetAmount }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('project.actualAmount')">
          {{ detail.project.actualAmount }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('project.taskCount')">
          {{ detail.project.taskCount }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('project.description')" :span="3">
          {{ detail.project.description || '-' }}
        </el-descriptions-item>
      </el-descriptions>

      <el-tabs v-model="activeDetailTab">
        <el-tab-pane :label="t('project.gantt')" name="gantt">
          <div class="gantt-wrap">
            <ProjectGantt :items="ganttItems" :loading="detail.loading" />
          </div>
        </el-tab-pane>
        <el-tab-pane name="rows">
          <template #label>
            {{ t('project.projectTask') }}
            <span class="bs-tab-count">({{ ganttItems.length }})</span>
          </template>
          <el-table :data="ganttItems" border stripe size="small">
            <el-table-column :label="t('project.name')" prop="taskName" min-width="150" />
            <el-table-column :label="t('project.groupCode')" prop="groupText" width="90" />
            <el-table-column :label="t('project.ownerName')" prop="ownerName" width="110" />
            <el-table-column :label="t('project.startDate')" prop="startDate" width="120" />
            <el-table-column :label="t('project.endDate')" prop="endDate" width="120" />
            <el-table-column :label="t('project.progress')" prop="progress" width="90" />
            <el-table-column :label="t('project.milestone')" width="90">
              <template #default="{ row }">
                <el-tag v-if="row.milestone" size="small" type="warning" effect="light" round>
                  {{ t('project.milestone') }}
                </el-tag>
                <span v-else>-</span>
              </template>
            </el-table-column>
            <el-table-column :label="t('project.source')" prop="source" width="90" />
            <el-table-column :label="t('common.action.operate')" width="110" fixed="right">
              <template #default="{ row }">
                <ActionBar
                  :actions="[
                    { key: 'edit', tip: 'common.action.edit', perm: 'project:edit' },
                    { key: 'delete', tip: 'common.action.delete', perm: 'project:edit', danger: true },
                  ]"
                  @select="
                    (k) => {
                      if (k === 'edit') openRow(row as unknown as ProjectTask)
                      else void removeRow(row as unknown as ProjectTask)
                    }
                  "
                />
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>
  </el-drawer>

  <!-- 新建 / 编辑项目 -->
  <el-dialog
    v-model="formDialog.visible"
    :title="formDialog.id ? t('project.edit') : formDialog.fromContract ? t('project.fromContract') : t('project.create')"
    width="var(--bs-layout-dialog-md)"
    append-to-body
  >
    <el-alert
      v-if="formDialog.fromContract"
      :title="t('project.fromContractHint')"
      type="info"
      :closable="false"
      class="form-hint"
    />
    <el-form :model="form" label-width="110px">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="t('project.name')">
            <el-input v-model="form.name" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('project.contractNo')">
            <ContractSelect
              v-model="form.contractId"
              :placeholder="t('project.selectContract')"
              @change="onContractChange"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('project.customerName')">
            <CustomerSelect v-model="form.customerId" @change="onCustomerChange" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('project.managerName')">
            <el-input v-model="form.managerName" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('project.deptName')">
            <el-input v-model="form.deptName" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('project.startDate')">
            <el-date-picker v-model="form.startDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('project.endDate')">
            <el-date-picker v-model="form.endDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('project.budgetAmount')">
            <el-input-number v-model="form.budgetAmount" :min="0" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('common.form.status')">
            <el-select v-model="form.status" style="width: 100%" :disabled="!formDialog.id">
              <el-option
                v-for="tab in statusTabs.filter((x) => x.value !== 'all')"
                :key="String(tab.value)"
                :label="t(tab.labelKey || '')"
                :value="tab.value"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <el-form-item :label="t('project.description')">
            <el-input v-model="form.description" type="textarea" :rows="2" />
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <el-form-item :label="t('common.form.remark')">
            <el-input v-model="form.remark" type="textarea" :rows="2" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>
    <template #footer>
      <el-button @click="formDialog.visible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button :loading="formDialog.loading" @click="saveProject(false)">
        {{ t('common.action.saveDraft') }}
      </el-button>
      <el-button
        v-if="flowEnabled('project')"
        v-permission="'project:submit'"
        type="primary"
        :loading="formDialog.loading"
        @click="saveProject(true)"
      >
        {{ t('common.action.submitApproval') }}
      </el-button>
    </template>
  </el-dialog>

  <!-- 生成甘特 -->
  <el-dialog v-model="generateDialog.visible" :title="t('project.generateGantt')" width="var(--bs-layout-dialog-sm)" append-to-body>
    <el-alert :title="t('project.generateGanttHint')" type="info" :closable="false" class="form-hint" />
    <el-form :model="generateForm" label-width="120px">
      <el-form-item :label="t('project.groupCode')">
        <el-select v-model="generateForm.groupCode" clearable style="width: 100%">
          <el-option
            v-for="opt in GROUP_OPTIONS"
            :key="opt.value"
            :label="t(opt.labelKey)"
            :value="opt.value"
          />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('project.auto')">
        <el-switch v-model="generateForm.overwrite" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="generateDialog.visible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="generateDialog.loading" @click="runGenerate">
        {{ t('project.generateGantt') }}
      </el-button>
    </template>
  </el-dialog>

  <!-- 甘特行编辑 -->
  <el-dialog
    v-model="rowDialog.visible"
    :title="rowDialog.id ? t('common.action.edit') : t('project.addTask')"
    width="var(--bs-layout-dialog-md)"
    append-to-body
  >
    <el-form :model="rowForm" label-width="110px">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="t('project.name')">
            <el-input v-model="rowForm.taskName" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('project.groupCode')">
            <el-select v-model="rowForm.groupCode" clearable style="width: 100%">
              <el-option
                v-for="opt in GROUP_OPTIONS"
                :key="opt.value"
                :label="t(opt.labelKey)"
                :value="opt.value"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('project.ownerName')">
            <el-input v-model="rowForm.ownerName" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('project.startDate')">
            <el-date-picker v-model="rowForm.startDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('project.endDate')">
            <el-date-picker v-model="rowForm.endDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('project.progress')">
            <el-input-number v-model="rowForm.progress" :min="0" :max="100" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('project.weight')">
            <el-input-number v-model="rowForm.weight" :min="0" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('common.form.status')">
            <el-select v-model="rowForm.status" style="width: 100%">
              <el-option
                v-for="opt in ROW_STATUS"
                :key="opt.value"
                :label="t(opt.labelKey)"
                :value="opt.value"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('project.milestone')">
            <el-switch v-model="rowForm.milestone" />
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <el-form-item :label="t('common.form.remark')">
            <el-input v-model="rowForm.remark" type="textarea" :rows="2" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>
    <template #footer>
      <el-button @click="rowDialog.visible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="rowDialog.loading" @click="saveRow">
        {{ t('common.action.save') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.project-detail {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  height: 100%;
  min-height: 0;
}

.detail-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.detail-head-actions {
  display: flex;
  gap: var(--bs-space-2);
}

.gantt-wrap {
  height: 420px;
  min-height: 0;
}

.form-hint {
  margin-bottom: var(--bs-space-3);
}
</style>
