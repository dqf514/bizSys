<script setup lang="ts">
import { computed, defineAsyncComponent, onActivated, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import TaskDetailPanel from '../components/TaskDetailPanel.vue'
// echarts 体积较大，甘特组件按需异步加载
// eslint-disable-next-line @typescript-eslint/no-unused-vars -- template 中作为组件使用
const TaskGantt = defineAsyncComponent(() => import('../components/TaskGantt.vue'))
import { useListPage } from '@/composables/useListPage'
import { listTasks, taskCounts, exportTasks } from '@/api/task'
import type { Task } from '@/api/types'

defineOptions({ name: 'TaskList' })

const { t } = useI18n()
const router = useRouter()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'task.task.searchName', placeholderKey: 'task.task.placeholderName', width: 220 },
  { key: 'customerName', labelKey: 'task.task.searchCustomer', placeholderKey: 'task.task.placeholderCustomer', width: 180 },
]

const counts = ref<Record<string, number>>({})

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'draft', labelKey: 'task.task.statusDraft', count: 0 },
  { value: 'approving', labelKey: 'task.task.statusApproving', count: 0 },
  { value: 'rejected', labelKey: 'task.task.statusRejected', count: 0 },
  { value: 'in_progress', labelKey: 'task.task.statusInProgress', count: 0 },
  { value: 'finished', labelKey: 'task.task.statusFinished', count: 0 },
  { value: 'settled', labelKey: 'task.task.statusSettled', count: 0 },
  { value: 'stopped', labelKey: 'task.task.statusStopped', count: 0 },
])

const list = useListPage<Task>({
  fetch: async (params) => {
    const data = await listTasks({
      ...params,
      q: searchModel.value.q || undefined,
      filters: { customerName: searchModel.value.customerName || undefined },
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) =>
    exportTasks({
      ...params,
      q: searchModel.value.q || undefined,
      filters: { customerName: searchModel.value.customerName || undefined },
    }),
  defaultStatus: 'all',
  onLoaded: () => {
    void loadCounts()
  },
})

async function loadCounts() {
  try {
    counts.value = (await taskCounts()) ?? {}
    let all = 0
    for (const tab of statusTabs.value) {
      if (tab.value === 'all') continue
      tab.count = counts.value[tab.value] ?? 0
      all += tab.count
    }
    const allTab = statusTabs.value.find((x) => x.value === 'all')
    if (allTab) allTab.count = all
  } catch {
    /* counts optional */
  }
}

onMounted(() => void loadCounts())

/* ---------- 列表 / 甘特 视图切换 ---------- */
type ViewMode = 'list' | 'gantt'
const viewMode = ref<ViewMode>('list')
const viewOptions = computed(() => [
  { label: t('task.task.viewList'), value: 'list' },
  { label: t('task.task.viewGantt'), value: 'gantt' },
])

const ganttTasks = ref<Task[]>([])
const ganttLoading = ref(false)

async function loadGantt() {
  ganttLoading.value = true
  try {
    const data = await listTasks({
      page: 1,
      size: 200,
      q: searchModel.value.q || undefined,
      status: list.query.status as string | undefined,
      filters: { customerName: searchModel.value.customerName || undefined },
    })
    ganttTasks.value = data.items ?? []
  } catch {
    ganttTasks.value = []
  } finally {
    ganttLoading.value = false
  }
}

function switchView(mode: ViewMode) {
  viewMode.value = mode
  if (mode === 'gantt') void loadGantt()
}

function onSearch() {
  if (viewMode.value === 'gantt') void loadGantt()
  else list.search()
}

function onReset() {
  searchModel.value = { q: '', customerName: '' }
  if (viewMode.value === 'gantt') void loadGantt()
  else list.reset()
}

function onStatusChange(status: string) {
  if (viewMode.value === 'gantt') {
    list.query.status = status
    void loadGantt()
  } else {
    list.setStatus(status)
  }
}

// keep-alive 重新进入时刷新甘特（列表模式由 useListPage 内部处理）
onActivated(() => {
  if (viewMode.value === 'gantt') void loadGantt()
})

const columns: ListColumn[] = [
  { prop: 'taskNo', labelKey: 'task.task.taskNo', width: 150, fixed: 'left', sortable: 'task_no' },
  { prop: 'taskTypeLabel', labelKey: 'task.task.taskType', width: 110, sortable: 'task_type' },
  { prop: 'customerName', labelKey: 'task.task.customerName', minWidth: 140, sortable: 'customer_name' },
  {
    prop: 'bizBlock',
    labelKey: 'task.task.bizBlockDept',
    minWidth: 140,
    sortable: 'biz_block',
    formatter: (row) => [row.bizBlockLabel || row.bizBlock, row.deptName].filter(Boolean).join(' / ') || '-',
  },
  { prop: 'status', labelKey: 'task.task.status', width: 120, sortable: 'status' },
  { prop: 'ownerName', labelKey: 'task.task.ownerName', width: 100 },
  { prop: 'updateTime', labelKey: 'task.task.updateTime', width: 160, sortable: 'update_time' },
]

function openCreate() {
  router.push('/task/tasks/new')
}

/* ---------- 详情抽屉 ---------- */
const drawerVisible = ref(false)
const drawerTaskId = ref(0)
const drawerTask = ref<Task | null>(null)

function openDetail(row: Task) {
  drawerTask.value = null
  drawerTaskId.value = row.id
  drawerVisible.value = true
}

function onDetailChanged() {
  if (viewMode.value === 'gantt') void loadGantt()
  list.refresh()
}
</script>

<template>
  <ListPage :title="t('task.task.title')" :loading="list.loading.value && viewMode === 'list'">
    <template #actions>
      <el-segmented
        :model-value="viewMode"
        :options="viewOptions"
        @update:model-value="switchView($event as ViewMode)"
      />
      <el-button v-permission="'task:create'" type="primary" @click="openCreate">
        {{ t('task.task.create') }}
      </el-button>
      <ExportButton v-permission="'task:list:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="onSearch"
        @reset="onReset"
      />
    </template>

    <template #statusTabs>
      <StatusTabs
        :tabs="statusTabs"
        :model-value="String(list.query.status)"
        @update:model-value="onStatusChange($event)"
      />
    </template>

    <template #table>
      <ListTable
        v-if="viewMode === 'list'"
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
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="task.task.status" />
          <StatusTag
            v-if="row.settleStatus === 'invoiced' || row.settleStatus === 'paid'"
            :status="String(row.settleStatus)"
            i18n-prefix="finance.settlement.status"
            class="settle-badge"
          />
        </template>
        <template #taskNo="{ row }">
          <el-button link type="primary" @click="openDetail(row as unknown as Task)">{{ row.taskNo || '-' }}</el-button>
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="90" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar
                :actions="[{ key: 'detail', tip: 'common.action.detail' }]"
                @select="openDetail(row as unknown as Task)"
              />
            </template>
          </el-table-column>
        </template>
      </ListTable>
      <TaskGantt v-else :tasks="ganttTasks" :loading="ganttLoading" @open="openDetail" />
    </template>

    <el-drawer v-model="drawerVisible" size="70%" destroy-on-close>
      <template #header>
        <span class="drawer-title">
          {{ drawerTask?.taskName || t('task.task.detail') }}
          <StatusTag v-if="drawerTask" :status="drawerTask.status" i18n-prefix="task.task.status" />
        </span>
      </template>
      <TaskDetailPanel
        v-if="drawerTaskId"
        :task-id="drawerTaskId"
        @loaded="drawerTask = $event"
        @changed="onDetailChanged"
        @removed="drawerVisible = false"
      />
    </el-drawer>
  </ListPage>
</template>

<style scoped>
.drawer-title {
  display: inline-flex;
  align-items: center;
  gap: var(--bs-space-2);
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.settle-badge {
  margin-left: var(--bs-space-1);
}
</style>
