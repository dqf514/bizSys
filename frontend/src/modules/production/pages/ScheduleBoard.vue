<script setup lang="ts">
/**
 * 智能排程甘特（B5 CSV 22）。
 *
 * 流程：自动排期生成方案（draft）→ 人工调整排程行 → 发布（占用资源）→ 确认开工。
 * 排程求解读取任务上的七维分配：人 / 机 / 样车按时段独占，物料按可用量校验。
 */
import { defineAsyncComponent, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import BackButton from '@/components/common/BackButton.vue'
import { useListPage } from '@/composables/useListPage'
import {
  autoSchedule,
  cancelPlan,
  confirmSchedule,
  deletePlan,
  deleteSchedule,
  exportSchedules,
  getPlan,
  listPlans,
  planCounts,
  publishPlan,
  resourceOccupancy,
  updateSchedule,
} from '@/api/production'
import { listProjects } from '@/api/project'
import type { ProdPlan, ProdSchedule, Project, ResourceOccupancy } from '@/api/types'

// echarts 体积较大，甘特组件按需异步加载
// eslint-disable-next-line @typescript-eslint/no-unused-vars -- template 中作为组件使用
const ScheduleGantt = defineAsyncComponent(() => import('../components/ScheduleGantt.vue'))

defineOptions({ name: 'ScheduleBoard' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'production.schedule.planName', placeholderKey: 'production.schedule.planName', width: 220 },
]

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'draft', labelKey: 'production.status.draft', count: 0 },
  { value: 'published', labelKey: 'production.status.published', count: 0 },
  { value: 'confirmed', labelKey: 'production.status.confirmed', count: 0 },
  { value: 'cancelled', labelKey: 'production.status.cancelled', count: 0 },
])

const list = useListPage<ProdPlan>({
  fetch: async (params) => {
    const data = await listPlans({
      ...params,
      q: searchModel.value.q || undefined,
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) => exportSchedules({ ...params, q: searchModel.value.q || undefined }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

async function loadCounts() {
  try {
    const counts = (await planCounts()) ?? {}
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
  { prop: 'planNo', labelKey: 'production.schedule.planNo', width: 150, sortable: 'plan_no' },
  { prop: 'name', labelKey: 'production.schedule.planName', minWidth: 180 },
  { prop: 'planDate', labelKey: 'production.schedule.planDate', width: 120, sortable: 'plan_date' },
  { prop: 'taskCount', labelKey: 'production.schedule.taskCount', width: 90, align: 'right' },
  { prop: 'scheduleCount', labelKey: 'production.schedule.scheduleCount', width: 110, align: 'right' },
  { prop: 'conflictCount', labelKey: 'production.schedule.conflictCount', width: 90, align: 'right' },
  { prop: 'statusText', labelKey: 'production.schedule.statusLabel', width: 100 },
  { prop: 'generatedByName', labelKey: 'production.schedule.generatedBy', width: 110 },
  { prop: 'publishedAt', labelKey: 'production.schedule.publishedAt', width: 160 },
  { prop: 'createTime', labelKey: 'common.form.createTime', width: 160, sortable: 'create_time' },
]

/** 方案状态 → 标签色 */
function planTagType(status: string): 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  if (status === 'published') return 'primary'
  if (status === 'confirmed') return 'success'
  if (status === 'cancelled') return 'info'
  return 'warning'
}

/* ---------------- 自动排期 ---------------- */

const autoDialog = reactive({ visible: false, loading: false })
const autoForm = reactive({
  name: '',
  baseDate: '',
  dateFrom: '',
  dateTo: '',
  projectId: '' as string | number,
  remark: '',
})
const projectOptions = ref<{ label: string; value: number }[]>([])

async function loadProjectOptions() {
  try {
    const data = await listProjects({ page: 1, size: 200 })
    projectOptions.value = (data.items ?? []).map((p: Project) => ({
      label: `${p.projectNo} ${p.name}`,
      value: p.id,
    }))
  } catch {
    projectOptions.value = []
  }
}

function openAuto() {
  autoForm.name = ''
  autoForm.baseDate = ''
  autoForm.dateFrom = ''
  autoForm.dateTo = ''
  autoForm.projectId = ''
  autoForm.remark = ''
  autoDialog.visible = true
  void loadProjectOptions()
}

async function runAutoSchedule() {
  autoDialog.loading = true
  try {
    const plan = await autoSchedule({
      name: autoForm.name || undefined,
      baseDate: autoForm.baseDate || undefined,
      dateFrom: autoForm.dateFrom || undefined,
      dateTo: autoForm.dateTo || undefined,
      projectId: autoForm.projectId ? Number(autoForm.projectId) : undefined,
      remark: autoForm.remark,
    })
    ElMessage.success(t('production.schedule.autoSuccess'))
    autoDialog.visible = false
    list.refresh()
    if (plan?.id) openDetail(plan.id)
  } catch {
    /* http notifies */
  } finally {
    autoDialog.loading = false
  }
}

/* ---------------- 方案详情 ---------------- */

const detail = reactive({ visible: false, loading: false, plan: null as ProdPlan | null })
const schedules = ref<ProdSchedule[]>([])
const activeDetailTab = ref('gantt')


async function openDetail(id: number) {
  detail.visible = true
  detail.loading = true
  activeDetailTab.value = 'gantt'
  try {
    const plan = await getPlan(id)
    detail.plan = plan
    schedules.value = plan.schedules ?? []
  } catch {
    detail.plan = null
    schedules.value = []
  } finally {
    detail.loading = false
  }
}

function planActions(row: ProdPlan): ActionItem[] {
  const actions: ActionItem[] = [{ key: 'detail', tip: 'production.schedule.detail' }]
  if (row.status === 'draft' || row.status === 'published') {
    actions.push({ key: 'publish', tip: 'production.schedule.publish', perm: 'production:schedule:publish' })
    actions.push({ key: 'cancel', tip: 'production.schedule.cancelPlan', perm: 'production:schedule:publish' })
  }
  if (row.status !== 'confirmed') {
    actions.push({ key: 'delete', tip: 'common.action.delete', perm: 'production:schedule:delete', danger: true })
  }
  return actions
}

async function onPlanAction(key: string, row: ProdPlan) {
  try {
    if (key === 'detail') {
      openDetail(row.id)
      return
    }
    if (key === 'publish') {
      await publishPlan(row.id)
      ElMessage.success(t('production.schedule.published'))
      list.refresh()
      if (detail.visible && detail.plan?.id === row.id) await openDetail(row.id)
    } else if (key === 'cancel') {
      await cancelPlan(row.id)
      ElMessage.success(t('common.message.saveSuccess'))
      list.refresh()
      if (detail.visible && detail.plan?.id === row.id) await openDetail(row.id)
    } else if (key === 'delete') {
      await deletePlan(row.id)
      ElMessage.success(t('common.message.deleteSuccess'))
      list.refresh()
    }
  } catch {
    /* http notifies */
  }
}

/* ---------------- 排程行人工调整 ---------------- */

const adjustDialog = reactive({ visible: false, loading: false, row: null as ProdSchedule | null })
const adjustForm = reactive({
  resourceType: 'equipment' as ProdSchedule['resourceType'],
  resourceName: '',
  resourceCode: '',
  quantity: 1,
  unit: '',
  planStart: '',
  planEnd: '',
  status: 'scheduled' as ProdSchedule['status'],
  remark: '',
})

const RESOURCE_TYPES = [
  { value: 'equipment', labelKey: 'production.resourceType.equipment' },
  { value: 'person', labelKey: 'production.resourceType.person' },
  { value: 'vehicle', labelKey: 'production.resourceType.vehicle' },
  { value: 'material', labelKey: 'production.resourceType.material' },
]

const SCHEDULE_STATUS = [
  { value: 'scheduled', labelKey: 'production.status.scheduled' },
  { value: 'published', labelKey: 'production.status.published' },
  { value: 'confirmed', labelKey: 'production.status.confirmed' },
  { value: 'done', labelKey: 'production.status.done' },
  { value: 'cancelled', labelKey: 'production.status.cancelled' },
]

function openAdjust(row: ProdSchedule) {
  adjustForm.resourceType = row.resourceType
  adjustForm.resourceName = row.resourceName
  adjustForm.resourceCode = row.resourceCode
  adjustForm.quantity = row.quantity
  adjustForm.unit = row.unit
  adjustForm.planStart = row.planStart ? row.planStart.slice(0, 19).replace(' ', 'T') : ''
  adjustForm.planEnd = row.planEnd ? row.planEnd.slice(0, 19).replace(' ', 'T') : ''
  adjustForm.status = row.status
  adjustForm.remark = row.remark
  adjustDialog.row = row
  adjustDialog.visible = true
}

async function saveAdjust() {
  const row = adjustDialog.row
  if (!row) return
  adjustDialog.loading = true
  try {
    await updateSchedule(row.id, {
      resourceType: adjustForm.resourceType,
      resourceName: adjustForm.resourceName,
      resourceCode: adjustForm.resourceCode,
      quantity: adjustForm.quantity,
      unit: adjustForm.unit,
      planStart: adjustForm.planStart ? new Date(adjustForm.planStart).toISOString().slice(0, 19) : undefined,
      planEnd: adjustForm.planEnd ? new Date(adjustForm.planEnd).toISOString().slice(0, 19) : undefined,
      status: adjustForm.status,
      remark: adjustForm.remark,
      version: row.version,
    })
    ElMessage.success(t('common.message.saveSuccess'))
    adjustDialog.visible = false
    await openDetail(row.planId ?? 0)
  } catch {
    /* http notifies */
  } finally {
    adjustDialog.loading = false
  }
}

async function onScheduleAction(key: string, row: ProdSchedule) {
  try {
    if (key === 'adjust') {
      openAdjust(row)
      return
    }
    if (key === 'confirm') {
      await confirmSchedule(row.id)
      ElMessage.success(t('common.message.saveSuccess'))
      await openDetail(row.planId ?? 0)
    } else if (key === 'delete') {
      await deleteSchedule(row.id)
      ElMessage.success(t('common.message.deleteSuccess'))
      await openDetail(row.planId ?? 0)
    }
  } catch {
    /* http notifies */
  }
}

function scheduleActions(row: ProdSchedule): ActionItem[] {
  const actions: ActionItem[] = [
    { key: 'adjust', tip: 'production.schedule.manualAdjust', perm: 'production:schedule:edit' },
  ]
  if (row.status === 'published' || row.status === 'scheduled') {
    actions.push({
      key: 'confirm',
      tip: 'production.schedule.confirmSchedule',
      perm: 'production:schedule:publish',
    })
  }
  if (row.status !== 'confirmed') {
    actions.push({
      key: 'delete',
      tip: 'common.action.delete',
      perm: 'production:schedule:delete',
      danger: true,
    })
  }
  return actions
}

/* ---------------- 资源占用视图 ---------------- */

const occupancy = ref<ResourceOccupancy[]>([])
const occupancyLoading = ref(false)
const occupancyType = ref('')

const RESOURCE_TYPE_OPTIONS = [
  { value: '', labelKey: 'production.schedule.resourceType' },
  { value: 'equipment', labelKey: 'production.resourceType.equipment' },
  { value: 'person', labelKey: 'production.resourceType.person' },
  { value: 'vehicle', labelKey: 'production.resourceType.vehicle' },
  { value: 'material', labelKey: 'production.resourceType.material' },
]

async function loadOccupancy() {
  occupancyLoading.value = true
  try {
    const data = await resourceOccupancy(
      occupancyType.value ? { resourceType: occupancyType.value } : {},
    )
    occupancy.value = data.items ?? []
  } catch {
    occupancy.value = []
  } finally {
    occupancyLoading.value = false
  }
}

watch(
  () => activeDetailTab.value,
  (v) => {
    if (v === 'occupancy') void loadOccupancy()
  },
)

</script>

<template>
  <ListPage :title="t('production.schedule.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'production:schedule:auto'" type="primary" size="small" @click="openAuto">
        {{ t('production.schedule.autoSchedule') }}
      </el-button>
      <ExportButton v-permission="'production:schedule:list:export'" :export-fn="() => list.exportList()" />
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
        :page="list.pagination.value.page"
        :size="list.pagination.value.size"
        @update:page="list.setPage"
        @update:size="list.setSize"
        @sort-change="list.onSortChange"
      >
        <template #statusText="{ row }">
          <el-tag size="small" effect="light" round :type="planTagType(String(row.status))">
            {{ row.statusText || row.status }}
          </el-tag>
        </template>
        <template #conflictCount="{ row }">
          <span :class="{ 'is-conflict': Number(row.conflictCount) > 0 }">{{ row.conflictCount }}</span>
        </template>
        <template #operate="{ row }">
          <ActionBar :actions="planActions(row)" @select="(k) => onPlanAction(k, row)" />
        </template>
      </ListTable>
    </template>
  </ListPage>

  <!-- 方案详情抽屉 -->
  <el-drawer
    v-model="detail.visible"
    :title="detail.plan ? `${detail.plan.planNo} · ${detail.plan.name}` : t('production.schedule.detail')"
    size="var(--bs-layout-drawer-xl)"
    append-to-body
  >
    <div v-loading="detail.loading" class="plan-detail">
      <div class="detail-head">
        <BackButton @click="detail.visible = false" />
        <div class="detail-head-actions">
          <el-button
            v-permission="'production:schedule:publish'"
            size="small"
            type="primary"
            plain
            :disabled="!detail.plan || !['draft', 'published'].includes(detail.plan.status)"
            @click="onPlanAction('publish', detail.plan!)"
          >
            {{ t('production.schedule.publish') }}
          </el-button>
        </div>
      </div>

      <el-descriptions v-if="detail.plan" :column="3" border size="small">
        <el-descriptions-item :label="t('production.schedule.planDate')">
          {{ detail.plan.planDate || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('production.schedule.taskCount')">
          {{ detail.plan.taskCount }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('production.schedule.conflictCount')">
          {{ detail.plan.conflictCount }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('production.schedule.generatedBy')">
          {{ detail.plan.generatedByName || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('production.schedule.publishedAt')">
          {{ detail.plan.publishedAt || '-' }}
        </el-descriptions-item>
        <el-descriptions-item :label="t('production.schedule.autoGenerated')">
          {{ detail.plan.autoGenerated ? t('production.schedule.auto') : t('production.schedule.manual') }}
        </el-descriptions-item>
      </el-descriptions>

      <el-alert
        v-if="detail.plan && detail.plan.conflictCount > 0"
        type="warning"
        :closable="false"
        :title="t('production.schedule.conflictTip')"
        class="conflict-alert"
      />

      <el-tabs v-model="activeDetailTab">
        <el-tab-pane :label="t('production.schedule.occupancy')" name="gantt">
          <div class="gantt-wrap">
            <ScheduleGantt :schedules="schedules" :loading="detail.loading" />
          </div>
        </el-tab-pane>
        <el-tab-pane name="rows">
          <template #label>
            {{ t('production.schedule.scheduleCount') }}
            <span class="bs-tab-count">({{ schedules.length }})</span>
          </template>
          <el-table :data="schedules" border stripe size="small">
            <el-table-column :label="t('production.schedule.planNo')" prop="scheduleNo" width="150" />
            <el-table-column :label="t('task.task.taskNo')" prop="taskNo" width="140" />
            <el-table-column :label="t('task.task.taskName')" prop="taskName" min-width="140" show-overflow-tooltip />
            <el-table-column :label="t('production.schedule.resourceType')" prop="resourceTypeText" width="90" />
            <el-table-column :label="t('production.schedule.resourceName')" prop="resourceName" min-width="120" />
            <el-table-column :label="t('production.schedule.quantity')" prop="quantity" width="80" />
            <el-table-column :label="t('production.schedule.planStart')" prop="planStart" width="150" />
            <el-table-column :label="t('production.schedule.planEnd')" prop="planEnd" width="150" />
            <el-table-column :label="t('production.schedule.statusLabel')" prop="statusText" width="90" />
            <el-table-column :label="t('production.schedule.source')" prop="source" width="80" />
            <el-table-column :label="t('production.schedule.conflictReason')" prop="conflictReason" min-width="140" />
            <el-table-column :label="t('common.action.operate')" width="130" fixed="right">
              <template #default="{ row }">
                <ActionBar :actions="scheduleActions(row)" @select="(k) => onScheduleAction(k, row)" />
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>
        <el-tab-pane :label="t('production.schedule.occupancyTitle')" name="occupancy">
          <div class="occupancy-toolbar">
            <el-select v-model="occupancyType" style="width: 180px" @change="loadOccupancy">
              <el-option
                v-for="opt in RESOURCE_TYPE_OPTIONS"
                :key="opt.value"
                :label="t(opt.labelKey)"
                :value="opt.value"
              />
            </el-select>
          </div>
          <el-table :data="occupancy" border stripe size="small" v-loading="occupancyLoading">
            <el-table-column :label="t('production.schedule.resourceType')" prop="resourceTypeText" width="100" />
            <el-table-column :label="t('production.schedule.resourceName')" prop="resourceName" min-width="150" />
            <el-table-column :label="t('production.schedule.resourceCode')" prop="resourceCode" width="140" />
            <el-table-column :label="t('production.schedule.occupiedHours')" prop="occupiedHours" width="110" />
            <el-table-column :label="t('production.schedule.windowCount')" prop="taskCount" width="100" />
          </el-table>
        </el-tab-pane>
      </el-tabs>
    </div>
  </el-drawer>

  <!-- 自动排期弹窗 -->
  <el-dialog v-model="autoDialog.visible" :title="t('production.schedule.autoScheduleTitle')" width="var(--bs-layout-dialog-md)" append-to-body>
    <el-alert :title="t('production.schedule.autoScheduleHint')" type="info" :closable="false" class="auto-hint" />
    <el-form :model="autoForm" label-width="120px">
      <el-form-item :label="t('production.schedule.planName')">
        <el-input v-model="autoForm.name" />
      </el-form-item>
      <el-form-item :label="t('production.schedule.baseDate')">
        <el-date-picker v-model="autoForm.baseDate" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
      </el-form-item>
      <el-form-item :label="t('production.schedule.scopeProject')">
        <el-select v-model="autoForm.projectId" clearable filterable style="width: 100%">
          <el-option
            v-for="opt in projectOptions"
            :key="String(opt.value)"
            :label="opt.label"
            :value="opt.value"
          />
        </el-select>
        <div class="field-hint">{{ t('production.schedule.scopeProjectHint') }}</div>
      </el-form-item>
      <el-form-item :label="t('common.form.startDate')">
        <el-date-picker
          v-model="autoForm.dateFrom"
          type="date"
          value-format="YYYY-MM-DD"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item :label="t('common.form.endDate')">
        <el-date-picker v-model="autoForm.dateTo" type="date" value-format="YYYY-MM-DD" style="width: 100%" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="autoDialog.visible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="autoDialog.loading" @click="runAutoSchedule">
        {{ t('production.schedule.autoSchedule') }}
      </el-button>
    </template>
  </el-dialog>

  <!-- 排程行调整弹窗 -->
  <el-dialog
    v-model="adjustDialog.visible"
    :title="t('production.schedule.manualAdjust')"
    width="var(--bs-layout-dialog-md)"
    append-to-body
  >
    <el-form :model="adjustForm" label-width="120px">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="t('production.schedule.resourceType')">
            <el-select v-model="adjustForm.resourceType" style="width: 100%">
              <el-option
                v-for="opt in RESOURCE_TYPES"
                :key="opt.value"
                :label="t(opt.labelKey)"
                :value="opt.value"
              />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('production.schedule.resourceName')">
            <el-input v-model="adjustForm.resourceName" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('production.schedule.resourceCode')">
            <el-input v-model="adjustForm.resourceCode" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('production.schedule.quantity')">
            <el-input-number v-model="adjustForm.quantity" :min="0" style="width: 100%" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('production.schedule.planStart')">
            <el-date-picker
              v-model="adjustForm.planStart"
              type="datetime"
              value-format="YYYY-MM-DDTHH:mm:ss"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('production.schedule.planEnd')">
            <el-date-picker
              v-model="adjustForm.planEnd"
              type="datetime"
              value-format="YYYY-MM-DDTHH:mm:ss"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('production.schedule.statusLabel')">
            <el-select v-model="adjustForm.status" style="width: 100%">
              <el-option
                v-for="opt in SCHEDULE_STATUS"
                :key="opt.value"
                :label="t(opt.labelKey)"
                :value="opt.value"
              />
            </el-select>
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>
    <template #footer>
      <el-button @click="adjustDialog.visible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="adjustDialog.loading" @click="saveAdjust">
        {{ t('common.action.save') }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.plan-detail {
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

.conflict-alert {
  margin: 0;
}

.gantt-wrap {
  height: 420px;
  min-height: 0;
}

.occupancy-toolbar {
  display: flex;
  gap: var(--bs-space-2);
  margin-bottom: var(--bs-space-2);
}

.auto-hint {
  margin-bottom: var(--bs-space-3);
}

.field-hint {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  line-height: 1.4;
}

.is-conflict {
  color: var(--bs-color-semantic-danger);
  font-weight: 600;
}
</style>
