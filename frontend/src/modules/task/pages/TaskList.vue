<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useListPage } from '@/composables/useListPage'
import { listTasks, taskCounts, deleteTask, taskAction, exportTasks, type TaskAction } from '@/api/task'
import type { Task, TaskStatus } from '@/api/types'

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
  { value: 'draft', labelKey: 'task.task.statusDraft', count: 0 },
  { value: 'assigning', labelKey: 'task.task.statusAssigning', count: 0 },
  { value: 'assigned', labelKey: 'task.task.statusAssigned', count: 0 },
  { value: 'in_progress', labelKey: 'task.task.statusInProgress', count: 0 },
  { value: 'finished', labelKey: 'task.task.statusFinished', count: 0 },
  { value: 'closed', labelKey: 'task.task.statusClosed', count: 0 },
  { value: 'stopped', labelKey: 'task.task.statusStopped', count: 0 },
  { value: 'all', labelKey: 'common.action.all', count: 0 },
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

const columns: ListColumn[] = [
  { prop: 'taskNo', labelKey: 'task.task.taskNo', width: 150, fixed: 'left' },
  { prop: 'taskName', labelKey: 'task.task.taskName', minWidth: 180, fixed: 'left' },
  { prop: 'taskTypeLabel', labelKey: 'task.task.taskType', width: 110 },
  { prop: 'customerName', labelKey: 'task.task.customerName', minWidth: 140 },
  { prop: 'contractNo', labelKey: 'task.task.contractNo', width: 140 },
  { prop: 'bizBlockLabel', labelKey: 'task.task.bizBlock', width: 110 },
  { prop: 'deptName', labelKey: 'task.task.deptName', width: 110 },
  { prop: 'ownerName', labelKey: 'task.task.ownerName', width: 100 },
  { prop: 'receiver', labelKey: 'task.task.receiver', width: 100 },
  { prop: 'receiverUnit', labelKey: 'task.task.receiverUnit', width: 120 },
  { prop: 'partySystem', labelKey: 'task.task.partySystem', width: 110 },
  { prop: 'planFinishDate', labelKey: 'task.task.planFinishDate', width: 120 },
  { prop: 'reportCount', labelKey: 'task.task.reportCount', width: 90 },
  { prop: 'sampleCount', labelKey: 'task.task.sampleCount', width: 90 },
  { prop: 'status', labelKey: 'task.task.status', width: 120 },
  { prop: 'createTime', labelKey: 'task.task.createTime', width: 160 },
  { prop: 'updateTime', labelKey: 'task.task.updateTime', width: 160 },
]

function openCreate() {
  router.push('/task/tasks/new')
}

function openEdit(row: Task) {
  router.push(`/task/tasks/${row.id}/edit`)
}

function openDetail(row: Task) {
  router.push(`/task/tasks/${row.id}`)
}

async function doAction(row: Task, action: TaskAction) {
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
  try {
    await taskAction(row.id, action)
    ElMessage.success(t('common.message.submitSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function remove(row: Task) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteTask(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

function availableActions(status: TaskStatus): { action: TaskAction; labelKey: string; type: string }[] {
  const map: Record<string, { action: TaskAction; labelKey: string; type: string }[]> = {
    draft: [
      { action: 'submit', labelKey: 'task.task.submit', type: 'warning' },
    ],
    assigning: [],
    assigned: [{ action: 'start', labelKey: 'task.task.start', type: 'primary' }],
    in_progress: [{ action: 'finish', labelKey: 'task.task.finish', type: 'success' }],
    finished: [{ action: 'close', labelKey: 'task.task.close', type: 'info' }],
  }
  return map[status] ?? []
}
</script>

<template>
  <ListPage :title="t('task.task.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'task:create'" type="primary" @click="openCreate">
        {{ t('task.task.create') }}
      </el-button>
      <ExportButton v-permission="'task:list:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="list.search()"
        @reset="searchModel = { q: '' }; list.reset()"
      />
    </template>

    <template #statusTabs>
      <StatusTabs
        :tabs="statusTabs"
        :model-value="String(list.query.status)"
        @update:model-value="list.setStatus($event)"
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
      >
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="task.task.status" />
        </template>
        <template #taskNo="{ row }">
          <el-button link type="primary" @click="openDetail(row as unknown as Task)">{{ row.taskNo }}</el-button>
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="260" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="row.status === 'draft'"
                v-permission="'task:edit'"
                link
                type="primary"
                @click="openEdit(row as unknown as Task)"
              >
                {{ t('common.action.edit') }}
              </el-button>
              <el-button
                v-for="a in availableActions(row.status as TaskStatus)"
                :key="a.action"
                v-permission="a.action === 'submit' ? 'task:assign' : 'task:edit'"
                link
                :type="a.type as any"
                @click="doAction(row as unknown as Task, a.action)"
              >
                {{ t(a.labelKey) }}
              </el-button>
              <el-button link type="primary" @click="openDetail(row as unknown as Task)">
                {{ t('common.action.detail') }}
              </el-button>
              <el-button
                v-if="row.status === 'draft'"
                v-permission="'task:edit'"
                link
                type="danger"
                @click="remove(row as unknown as Task)"
              >
                {{ t('common.action.delete') }}
              </el-button>
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>
</template>
