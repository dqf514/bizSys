<script setup lang="ts">
/** 工时填报：填报（按日填报，合同→任务联动，草稿/提交/退回）+ 我的工时（列表/筛选/导出）。 */
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useListPage } from '@/composables/useListPage'
import { useIsMobile } from '@/composables/useIsMobile'
import {
  createTimesheet,
  deleteTimesheet,
  exportMyTimesheets,
  getTimesheetDay,
  getTimesheetWeek,
  listMyTimesheets,
  myTimesheetCounts,
  searchTimesheetContracts,
  searchTimesheetTasks,
  updateTimesheet,
  withdrawTimesheet,
} from '@/api/hr'
import type { TimesheetPayload } from '@/api/hr'
import type {
  HrContractOption,
  HrTaskOption,
  HrTimesheetItem,
  HrWeekDay,
} from '@/api/types'

defineOptions({ name: 'TimesheetFill' })

const { t } = useI18n()
const { isMobile } = useIsMobile()
const ctrlSize = computed(() => (isMobile.value ? 'large' : 'default'))

const view = ref<'fill' | 'my'>('fill')

/* ================= 填报 ================= */

function fmt(d: Date) {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`
}
const todayStr = fmt(new Date())
const workDate = ref(todayStr)
const weekDays = ref<HrWeekDay[]>([])
const submittedItems = ref<HrTimesheetItem[]>([])
const dayTotal = ref(0)
const loadingDay = ref(false)

/** 填报行：草稿（id>0）与本地新行（id=0）同一结构渲染 */
interface RowState {
  id: number
  key: string
  contractId?: number
  taskId?: number
  hours: number
  content: string
  remark: string
  contractOptions: HrContractOption[]
  taskOptions: HrTaskOption[]
}

const draftRows = ref<RowState[]>([])
const newRows = ref<RowState[]>([])
let rowSeq = 0

function entryToRow(e: HrTimesheetItem): RowState {
  return {
    id: e.id,
    key: `e${e.id}`,
    contractId: e.contractId,
    taskId: e.taskId,
    hours: e.hours,
    content: e.content,
    remark: e.remark,
    contractOptions: [{ id: e.contractId, contractNo: e.contractNo, name: '', customerName: e.customerName }],
    taskOptions: [
      {
        id: e.taskId,
        taskNo: e.taskNo,
        taskName: e.taskName,
        contractId: e.contractId,
        contractNo: e.contractNo,
        customerName: e.customerName,
      },
    ],
  }
}

function blankRow(): RowState {
  return {
    id: 0,
    key: `n${++rowSeq}`,
    contractId: undefined,
    taskId: undefined,
    hours: 8,
    content: '',
    remark: '',
    contractOptions: [],
    taskOptions: [],
  }
}

async function loadDay() {
  loadingDay.value = true
  try {
    const data = await getTimesheetDay(workDate.value)
    draftRows.value = data.items.filter((i) => i.status === 'draft').map(entryToRow)
    submittedItems.value = data.items.filter((i) => i.status === 'submitted')
    dayTotal.value = data.totalHours
    newRows.value = []
  } catch {
    /* http notifies */
  } finally {
    loadingDay.value = false
  }
}

async function loadWeek() {
  try {
    weekDays.value = (await getTimesheetWeek(workDate.value)).days
  } catch {
    /* week strip optional */
  }
}

const WEEKDAYS = ['w1', 'w2', 'w3', 'w4', 'w5', 'w6', 'w7']

function shiftWeek(delta: number) {
  const d = new Date(`${workDate.value}T00:00:00`)
  d.setDate(d.getDate() + delta * 7)
  if (fmt(d) > todayStr) return
  workDate.value = fmt(d)
}

function pickDay(d: HrWeekDay) {
  if (d.future) return
  workDate.value = d.date
}

watch(workDate, () => {
  void loadDay()
  void loadWeek()
})

async function remoteContracts(q: string, row: RowState) {
  const opts = await searchTimesheetContracts(q)
  const keep = row.contractOptions.filter((o) => o.id === row.contractId)
  row.contractOptions = [...keep, ...opts.filter((o) => o.id !== row.contractId)]
}

async function remoteTasks(q: string, row: RowState) {
  if (!row.contractId) return
  const opts = await searchTimesheetTasks(row.contractId, q)
  const keep = row.taskOptions.filter((o) => o.id === row.taskId)
  row.taskOptions = [...keep, ...opts.filter((o) => o.id !== row.taskId)]
}

function onContractChange(row: RowState) {
  row.taskId = undefined
  row.taskOptions = []
}

function contractLabel(c: HrContractOption) {
  const base = `${c.contractNo} ${c.name}`.trim()
  return c.customerName ? `${base}（${c.customerName}）` : base
}

function taskLabelOf(x: HrTaskOption) {
  const base = `${x.taskNo} ${x.taskName}`.trim()
  return x.customerName ? `${base}（${x.customerName}）` : base
}

const saving = ref('')

async function saveRow(row: RowState, submit: boolean) {
  const payload: TimesheetPayload = {
    taskId: row.taskId ?? 0,
    workDate: workDate.value,
    hours: row.hours,
    content: row.content,
    remark: row.remark,
    submit,
  }
  if (!payload.taskId) {
    ElMessage.warning(t('hr.fill.needTask'))
    return
  }
  if (!payload.content.trim()) {
    ElMessage.warning(t('hr.fill.needContent'))
    return
  }
  saving.value = row.key
  try {
    if (row.id) await updateTimesheet(row.id, payload)
    else await createTimesheet(payload)
    ElMessage.success(t(submit ? 'hr.fill.submittedOk' : 'hr.fill.saved'))
    await Promise.all([loadDay(), loadWeek()])
    if (view.value === 'my') list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = ''
  }
}

async function withdrawEntry(e: HrTimesheetItem) {
  try {
    await ElMessageBox.confirm(t('hr.fill.withdrawConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await withdrawTimesheet(e.id)
    ElMessage.success(t('hr.fill.withdrawOk'))
    await Promise.all([loadDay(), loadWeek()])
  } catch {
    /* http notifies */
  }
}

async function removeRow(row: RowState) {
  if (!row.id) {
    newRows.value = newRows.value.filter((r) => r.key !== row.key)
    return
  }
  try {
    await ElMessageBox.confirm(t('hr.fill.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteTimesheet(row.id)
    ElMessage.success(t('hr.fill.deletedOk'))
    await Promise.all([loadDay(), loadWeek()])
  } catch {
    /* http notifies */
  }
}

onMounted(() => {
  void loadDay()
  void loadWeek()
})

/* ================= 我的工时 ================= */

const activeStatus = ref('all')
const counts = ref<Record<string, number>>({})
const statusTabs = computed<StatusTabItem[]>(() => [
  { value: 'all', labelKey: 'common.action.all', count: counts.value.all ?? 0 },
  { value: 'draft', label: t('hr.status.draft'), count: counts.value.draft ?? 0 },
  { value: 'submitted', label: t('hr.status.submitted'), count: counts.value.submitted ?? 0 },
])

async function loadCounts() {
  try {
    counts.value = (await myTimesheetCounts()) ?? {}
  } catch {
    /* counts optional */
  }
}

const searchModel = ref<Record<string, any>>({ q: '', month: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'hr.my.searchQ', placeholderKey: 'hr.my.placeholderQ', width: 220 },
  { key: 'month', labelKey: 'hr.my.month', type: 'month', width: 150 },
]

function monthRange(month: string): string {
  if (!month) return ''
  const [y, m] = month.split('-').map(Number)
  const last = new Date(y ?? 1970, m ?? 1, 0).getDate()
  return `${month}-01|${month}-${String(last).padStart(2, '0')}`
}

const list = useListPage<HrTimesheetItem>({
  fetch: async (params) => {
    const data = await listMyTimesheets({
      ...params,
      status: activeStatus.value === 'all' ? '' : activeStatus.value,
      q: searchModel.value.q || undefined,
      range: { work_date: monthRange(searchModel.value.month) },
    })
    return { items: data.items, total: data.total ?? 0 }
  },
  defaultStatus: 'all',
  onLoaded: () => void loadCounts(),
})

const myColumns: ListColumn[] = [
  { prop: 'workDate', labelKey: 'hr.my.workDate', width: 110, fixed: 'left', sortable: 'work_date' },
  { prop: 'taskName', labelKey: 'hr.my.task', minWidth: 180 },
  { prop: 'contractNo', labelKey: 'hr.my.contract', width: 150 },
  { prop: 'customerName', labelKey: 'hr.my.customer', minWidth: 140 },
  { prop: 'hours', labelKey: 'hr.my.hours', width: 90, sortable: 'hours' },
  { prop: 'content', labelKey: 'hr.my.content', minWidth: 200 },
  { prop: 'status', labelKey: 'hr.my.status', width: 96 },
  { prop: 'submittedAt', labelKey: 'hr.my.submittedAt', width: 165 },
  { prop: 'createTime', labelKey: 'hr.my.createTime', width: 165, sortable: 'create_time' },
]

function switchStatus(v: string) {
  activeStatus.value = v
  list.query.page = 1
  list.refresh()
}

function gotoFill(row: HrTimesheetItem) {
  workDate.value = row.workDate
  view.value = 'fill'
}

watch(view, (v) => {
  if (v === 'my') {
    void loadCounts()
    list.refresh()
  }
})
</script>

<template>
  <ListPage :title="t('hr.fill.title')" :loading="view === 'fill' ? loadingDay : list.loading.value">
    <template #actions>
      <ExportButton
        v-if="view === 'my'"
        v-permission="'hr:timesheet:list:export'"
        :export-fn="() =>
          exportMyTimesheets({
            status: activeStatus === 'all' ? '' : activeStatus,
            q: searchModel.q || undefined,
            range: { work_date: monthRange(searchModel.month) },
          })"
      />
      <el-button @click="view === 'fill' ? (loadDay(), loadWeek()) : list.refresh()">
        {{ t('common.action.refresh') }}
      </el-button>
    </template>

    <template #toolbar>
      <el-radio-group v-model="view" :size="ctrlSize">
        <el-radio-button value="fill">{{ t('hr.fill.tabFill') }}</el-radio-button>
        <el-radio-button value="my">{{ t('hr.fill.tabMy') }}</el-radio-button>
      </el-radio-group>
    </template>

    <!-- ============ 填报视图 ============ -->
    <div v-if="view === 'fill'" class="fill-view">
      <div class="date-bar">
        <el-button :size="ctrlSize" @click="shiftWeek(-1)">‹ {{ t('hr.fill.prevWeek') }}</el-button>
        <div class="week-strip">
          <button
            v-for="(d, i) in weekDays"
            :key="d.date"
            class="day-chip"
            :class="{ active: d.date === workDate, future: d.future, filled: d.count > 0 }"
            :disabled="d.future"
            :title="d.future ? t('hr.fill.futureDisabled') : d.date"
            @click="pickDay(d)"
          >
            <span class="day-w">{{ t(`hr.fill.${WEEKDAYS[i]}`) }}</span>
            <span class="day-n">{{ d.date.slice(5) }}</span>
            <span v-if="d.count > 0" class="day-h">{{ d.totalHours }}h</span>
          </button>
        </div>
        <el-button :size="ctrlSize" :disabled="workDate >= todayStr" @click="shiftWeek(1)">
          {{ t('hr.fill.nextWeek') }} ›
        </el-button>
        <el-date-picker
          v-model="workDate"
          type="date"
          value-format="YYYY-MM-DD"
          :disabled-date="(d: Date) => fmt(d) > todayStr"
          :size="ctrlSize"
          class="date-picker"
        />
        <el-button :size="ctrlSize" :disabled="workDate === todayStr" @click="workDate = todayStr">
          {{ t('hr.fill.today') }}
        </el-button>
      </div>

      <div v-if="!draftRows.length && !submittedItems.length && !newRows.length" class="empty-tip">
        {{ t('hr.fill.empty') }}
      </div>

      <!-- 草稿行 + 新行（同一可编辑结构） -->
      <div v-for="row in [...draftRows, ...newRows]" :key="row.key" class="ts-row">
        <div class="row-grid">
          <el-select
            :model-value="row.contractId"
            filterable
            remote
            :remote-method="(q: string) => remoteContracts(q, row)"
            :placeholder="t('hr.fill.searchContract')"
            :size="ctrlSize"
            class="cell-contract"
            @update:model-value="(v: number) => { row.contractId = v; onContractChange(row) }"
            @focus="remoteContracts('', row)"
          >
            <el-option v-for="c in row.contractOptions" :key="c.id" :label="contractLabel(c)" :value="c.id" />
          </el-select>
          <el-select
            v-model="row.taskId"
            filterable
            remote
            :disabled="!row.contractId"
            :remote-method="(q: string) => remoteTasks(q, row)"
            :placeholder="row.contractId ? t('hr.fill.searchTask') : t('hr.fill.selectContractFirst')"
            :size="ctrlSize"
            class="cell-task"
            @focus="remoteTasks('', row)"
          >
            <el-option v-for="x in row.taskOptions" :key="x.id" :label="taskLabelOf(x)" :value="x.id" />
          </el-select>
          <el-input-number v-model="row.hours" :min="0.5" :max="24" :step="0.5" :size="ctrlSize" class="cell-hours" />
          <el-input
            v-model="row.content"
            type="textarea"
            :rows="isMobile ? 2 : 1"
            autosize
            maxlength="500"
            :placeholder="t('hr.fill.contentPlaceholder')"
            :size="ctrlSize"
            class="cell-content"
          />
          <el-input
            v-model="row.remark"
            maxlength="500"
            :placeholder="t('hr.fill.remark')"
            :size="ctrlSize"
            class="cell-remark"
          />
          <div class="cell-actions">
            <el-button :size="ctrlSize" :loading="saving === row.key" @click="saveRow(row, false)">
              {{ t('hr.fill.saveDraft') }}
            </el-button>
            <el-button type="primary" :size="ctrlSize" :loading="saving === row.key" @click="saveRow(row, true)">
              {{ t('hr.fill.submitEntry') }}
            </el-button>
            <el-button
              :type="row.id ? 'danger' : 'default'"
              plain
              :size="ctrlSize"
              @click="removeRow(row)"
            >
              {{ row.id ? t('common.action.delete') : t('hr.fill.removeRow') }}
            </el-button>
          </div>
        </div>
      </div>

      <!-- 已提交行（只读 + 退回） -->
      <div v-for="e in submittedItems" :key="`s${e.id}`" class="ts-row readonly">
        <div class="row-grid">
          <div class="ro cell-contract">{{ e.contractNo }}</div>
          <div class="ro cell-task">{{ e.taskNo }} {{ e.taskName }}（{{ e.customerName }}）</div>
          <div class="ro cell-hours">{{ e.hours }}h</div>
          <div class="ro cell-content">{{ e.content }}</div>
          <div class="ro cell-remark">{{ e.remark || '-' }}</div>
          <div class="cell-actions">
            <StatusTag :status="e.status" i18n-prefix="hr.status" />
            <el-button type="warning" plain :size="ctrlSize" @click="withdrawEntry(e)">
              {{ t('hr.fill.withdraw') }}
            </el-button>
          </div>
        </div>
      </div>

      <div class="fill-footer">
        <el-button type="primary" plain :size="ctrlSize" class="add-btn" @click="newRows.push(blankRow())">
          + {{ t('hr.fill.addRow') }}
        </el-button>
        <span class="day-total">{{ t('hr.fill.dayTotal', { hours: dayTotal }) }}</span>
      </div>
    </div>

    <!-- ============ 我的工时视图 ============ -->
    <template v-if="view === 'my'">
      <div class="my-search">
        <SearchBar
          v-model="searchModel"
          :fields="searchFields"
          @search="list.search()"
          @reset="searchModel = { q: '', month: '' }; list.reset()"
        />
      </div>
      <StatusTabs :tabs="statusTabs" :model-value="activeStatus" @update:model-value="switchStatus" />
      <ListTable
        :columns="myColumns"
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
        <template #taskName="{ row }">
          <div class="cell-task-col">
            <span class="task-no">{{ row.taskNo }}</span>
            <span>{{ row.taskName }}</span>
          </div>
        </template>
        <template #content="{ row }">
          <span class="content-cell">{{ row.content }}</span>
        </template>
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="hr.status" />
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
              <ActionBar
                v-if="row.status === 'draft'"
                :actions="[{ key: 'edit', tip: 'hr.my.editInFill' }]"
                @select="gotoFill(row as HrTimesheetItem)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>
</template>

<style scoped>
.fill-view {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.date-bar {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  flex-wrap: wrap;
}

.week-strip {
  display: flex;
  gap: var(--bs-space-1);
  flex: 1;
  min-width: 0;
  overflow-x: auto;
}

.day-chip {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  min-width: 56px;
  padding: 6px 8px;
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  color: var(--bs-color-fg-default);
  cursor: pointer;
}

.day-chip.active {
  border-color: var(--bs-color-primary);
}

.day-chip.future {
  opacity: 0.45;
  cursor: not-allowed;
}

.day-chip .day-w {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.day-chip .day-h {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-primary);
  font-weight: 600;
}

.date-picker {
  width: 150px;
}

.empty-tip {
  padding: var(--bs-space-4);
  text-align: center;
  color: var(--bs-color-fg-muted);
  border: 1px dashed var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
}

.ts-row {
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  padding: var(--bs-space-2);
  background: var(--bs-color-bg-surface);
}

.row-grid {
  display: grid;
  grid-template-columns: minmax(220px, 1.1fr) minmax(220px, 1.1fr) 130px minmax(200px, 1.4fr) 140px auto;
  gap: var(--bs-space-2);
  align-items: center;
}

.cell-actions {
  display: flex;
  gap: var(--bs-space-1);
  align-items: center;
  white-space: nowrap;
}

.ro {
  color: var(--bs-color-fg-default);
  overflow: hidden;
  text-overflow: ellipsis;
}

.ro.cell-hours {
  font-weight: 600;
}

.fill-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bs-space-2);
}

.day-total {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.my-search {
  padding: var(--bs-space-2) var(--bs-space-3);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
}

.cell-task-col {
  display: flex;
  flex-direction: column;
}

.task-no {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.content-cell {
  display: inline-block;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

@media (max-width: 767px) {
  .row-grid {
    grid-template-columns: 1fr;
  }

  .cell-actions {
    flex-wrap: wrap;
  }

  .cell-actions .el-button {
    flex: 1;
    margin-left: 0;
  }

  .add-btn {
    width: 100%;
  }

  .fill-footer {
    flex-direction: column;
    align-items: stretch;
  }

  .day-total {
    text-align: center;
  }

  .date-picker {
    flex: 1;
    width: auto;
  }
}
</style>
