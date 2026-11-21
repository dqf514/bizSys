<script setup lang="ts">
/** 工时统计（管理视角）：按人员/任务/合同三维度汇总 + 筛选 + 导出 + 人员明细下钻。 */
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useIsMobile } from '@/composables/useIsMobile'
import {
  exportTimesheetStats,
  getTimesheetStats,
  getTimesheetStatsDetail,
  searchTimesheetStatsOptions,
} from '@/api/hr'
import type { HrStatsOption, HrStatsResult, HrStatsRow, HrTimesheetItem } from '@/api/types'

defineOptions({ name: 'TimesheetStats' })

const { t } = useI18n()
const { isMobile } = useIsMobile()
const ctrlSize = computed(() => (isMobile.value ? 'large' : 'default'))

type Dimension = 'user' | 'task' | 'contract'
const dimension = ref<Dimension>('user')
const dateRange = ref<[string, string] | null>(null)
const deptId = ref<number>()
const userId = ref<number>()
const taskId = ref<number>()

const deptOptions = ref<HrStatsOption[]>([])
const userOptions = ref<HrStatsOption[]>([])
const taskOptions = ref<HrStatsOption[]>([])

const stats = ref<HrStatsResult | null>(null)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    stats.value = await getTimesheetStats({
      dimension: dimension.value,
      dateStart: dateRange.value?.[0],
      dateEnd: dateRange.value?.[1],
      deptId: deptId.value,
      userId: userId.value,
      taskId: taskId.value,
    })
  } catch {
    /* http notifies */
  } finally {
    loading.value = false
  }
}

function resetFilters() {
  dateRange.value = null
  deptId.value = undefined
  userId.value = undefined
  taskId.value = undefined
  void load()
}

async function remoteUsers(q: string) {
  userOptions.value = await searchTimesheetStatsOptions('user', q)
}

async function remoteTasks(q: string) {
  taskOptions.value = await searchTimesheetStatsOptions('task', q)
}

function exportParams() {
  return {
    dimension: dimension.value,
    dateStart: dateRange.value?.[0],
    dateEnd: dateRange.value?.[1],
    deptId: deptId.value,
    userId: userId.value,
    taskId: taskId.value,
  }
}

/* ---------- 人员明细下钻 ---------- */
const drillVisible = ref(false)
const drillUser = ref<HrStatsRow | null>(null)
const drillItems = ref<HrTimesheetItem[]>([])
const drillTotal = ref(0)
const drillPage = ref(1)
const drillLoading = ref(false)

async function loadDrill() {
  if (!drillUser.value?.userId) return
  drillLoading.value = true
  try {
    const data = await getTimesheetStatsDetail({
      userId: drillUser.value.userId,
      dateStart: dateRange.value?.[0],
      dateEnd: dateRange.value?.[1],
      taskId: taskId.value,
      page: drillPage.value,
      size: 20,
    })
    drillItems.value = data.items
    drillTotal.value = data.total
  } catch {
    /* http notifies */
  } finally {
    drillLoading.value = false
  }
}

function openDrill(row: HrStatsRow) {
  drillUser.value = row
  drillPage.value = 1
  drillVisible.value = true
  void loadDrill()
}

onMounted(async () => {
  void load()
  deptOptions.value = await searchTimesheetStatsOptions('dept')
  void remoteUsers('')
  void remoteTasks('')
})
</script>

<template>
  <ListPage :title="t('hr.stats.title')" :loading="loading">
    <template #actions>
      <ExportButton v-permission="'hr:timesheet:stats:export'" :export-fn="() => exportTimesheetStats(exportParams())" />
      <el-button @click="load">{{ t('common.action.refresh') }}</el-button>
    </template>

    <div class="filter-bar">
      <el-radio-group
        v-model="dimension"
        :size="ctrlSize"
        @update:model-value="load"
      >
        <el-radio-button value="user">{{ t('hr.stats.dimensionUser') }}</el-radio-button>
        <el-radio-button value="task">{{ t('hr.stats.dimensionTask') }}</el-radio-button>
        <el-radio-button value="contract">{{ t('hr.stats.dimensionContract') }}</el-radio-button>
      </el-radio-group>
      <el-date-picker
        v-model="dateRange"
        type="daterange"
        value-format="YYYY-MM-DD"
        :start-placeholder="t('common.form.startDate')"
        :end-placeholder="t('common.form.endDate')"
        :size="ctrlSize"
        class="f-range"
        @update:model-value="load"
      />
      <el-select
        v-model="deptId"
        clearable
        filterable
        :placeholder="t('hr.stats.dept')"
        :size="ctrlSize"
        class="f-item"
        @update:model-value="load"
      >
        <el-option v-for="d in deptOptions" :key="d.id" :label="d.label" :value="d.id" />
      </el-select>
      <el-select
        v-model="userId"
        clearable
        filterable
        remote
        :remote-method="remoteUsers"
        :placeholder="t('hr.stats.searchUser')"
        :size="ctrlSize"
        class="f-item"
        @update:model-value="load"
      >
        <el-option v-for="u in userOptions" :key="u.id" :label="u.label" :value="u.id" />
      </el-select>
      <el-select
        v-model="taskId"
        clearable
        filterable
        remote
        :remote-method="remoteTasks"
        :placeholder="t('hr.stats.searchTask')"
        :size="ctrlSize"
        class="f-item"
        @update:model-value="load"
      >
        <el-option v-for="x in taskOptions" :key="x.id" :label="x.label" :value="x.id" />
      </el-select>
      <el-button :size="ctrlSize" @click="resetFilters">{{ t('common.action.reset') }}</el-button>
      <span class="tip">{{ t('hr.stats.onlySubmitted') }}</span>
    </div>

    <el-table v-if="dimension === 'user'" :data="stats?.rows ?? []" v-loading="loading" border>
      <el-table-column prop="userName" :label="t('hr.stats.userName')" min-width="120">
        <template #default="{ row }">
          <el-button link type="primary" @click="openDrill(row)">{{ row.userName }}</el-button>
        </template>
      </el-table-column>
      <el-table-column prop="deptName" :label="t('hr.stats.deptName')" min-width="120" />
      <el-table-column prop="totalHours" :label="t('hr.stats.totalHours')" width="130" sortable />
      <el-table-column prop="entryCount" :label="t('hr.stats.entryCount')" width="110" />
      <el-table-column prop="taskCount" :label="t('hr.stats.taskCount')" width="100" />
      <el-table-column prop="dayCount" :label="t('hr.stats.dayCount')" width="110" />
      <template #empty>{{ t('hr.stats.empty') }}</template>
    </el-table>

    <el-table v-else-if="dimension === 'task'" :data="stats?.rows ?? []" v-loading="loading" border>
      <el-table-column prop="taskNo" :label="t('hr.stats.taskNo')" width="150" />
      <el-table-column prop="taskName" :label="t('hr.stats.taskName')" min-width="180" />
      <el-table-column prop="contractNo" :label="t('hr.stats.contractNo')" width="150" />
      <el-table-column prop="customerName" :label="t('hr.stats.customerName')" min-width="140" />
      <el-table-column prop="totalHours" :label="t('hr.stats.totalHours')" width="130" sortable />
      <el-table-column prop="entryCount" :label="t('hr.stats.entryCount')" width="110" />
      <el-table-column prop="userCount" :label="t('hr.stats.userCount')" width="90" />
      <template #empty>{{ t('hr.stats.empty') }}</template>
    </el-table>

    <el-table v-else :data="stats?.rows ?? []" v-loading="loading" border>
      <el-table-column prop="contractNo" :label="t('hr.stats.contractNo')" width="150" />
      <el-table-column prop="customerName" :label="t('hr.stats.customerName')" min-width="160" />
      <el-table-column prop="totalHours" :label="t('hr.stats.totalHours')" width="130" sortable />
      <el-table-column prop="entryCount" :label="t('hr.stats.entryCount')" width="110" />
      <el-table-column prop="userCount" :label="t('hr.stats.userCount')" width="90" />
      <el-table-column prop="taskCount" :label="t('hr.stats.taskCount')" width="100" />
      <template #empty>{{ t('hr.stats.empty') }}</template>
    </el-table>

    <div v-if="stats" class="grand-total">{{ t('hr.stats.grandTotal', { hours: stats.grandTotalHours }) }}</div>

    <el-drawer
      v-model="drillVisible"
      :title="drillUser ? t('hr.stats.drillTitle', { name: drillUser.userName }) : ''"
      size="var(--bs-layout-drawer-lg)"
    >
      <el-table :data="drillItems" v-loading="drillLoading" border>
        <el-table-column prop="workDate" :label="t('hr.stats.workDate')" width="110" />
        <el-table-column prop="taskName" :label="t('hr.stats.taskName')" min-width="150">
          <template #default="{ row }">
            <div class="cell-task-col">
              <span class="task-no">{{ row.taskNo }}</span>
              <span>{{ row.taskName }}</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="contractNo" :label="t('hr.stats.contractNo')" width="140" />
        <el-table-column prop="hours" :label="t('hr.stats.totalHours')" width="100" />
        <el-table-column prop="content" :label="t('hr.stats.content')" min-width="160" show-overflow-tooltip />
        <el-table-column :label="t('hr.my.status')" width="90">
          <template #default="{ row }">
            <StatusTag :status="row.status" i18n-prefix="hr.status" />
          </template>
        </el-table-column>
      </el-table>
      <div class="drill-pager">
        <el-pagination
          layout="prev, pager, next, total"
          :total="drillTotal"
          :page-size="20"
          :current-page="drillPage"
          @current-change="(p: number) => { drillPage = p; loadDrill() }"
        />
      </div>
    </el-drawer>
  </ListPage>
</template>

<style scoped>
.filter-bar {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  flex-wrap: wrap;
  padding: var(--bs-space-2) var(--bs-space-3);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
}

.f-range {
  width: 260px;
}

.f-item {
  width: 180px;
}

.tip {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.grand-total {
  text-align: right;
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.cell-task-col {
  display: flex;
  flex-direction: column;
}

.task-no {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.drill-pager {
  display: flex;
  justify-content: flex-end;
  margin-top: var(--bs-space-2);
}

@media (max-width: 767px) {
  .f-range,
  .f-item {
    width: 100%;
  }
}
</style>
