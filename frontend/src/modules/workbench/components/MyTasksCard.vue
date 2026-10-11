<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import WidgetShell from './WidgetShell.vue'
import { useAuthStore } from '@/stores/auth'
import { listTasks } from '@/api/task'
import type { Task } from '@/api/types'

defineOptions({ name: 'MyTasksCard' })

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()

const items = ref<Task[]>([])
const total = ref(0)
const loading = ref(false)

const statusLabelKey: Record<string, string> = {
  draft: 'task.task.statusDraft',
  assigning: 'task.task.statusAssigning',
  assigned: 'task.task.statusAssigned',
  in_progress: 'task.task.statusInProgress',
  finished: 'task.task.statusFinished',
  closed: 'task.task.statusClosed',
  stopped: 'task.task.statusStopped',
  settled: 'task.task.statusSettled',
}

const tagType: Record<string, 'primary' | 'success' | 'warning' | 'info' | 'danger'> = {
  assigning: 'warning',
  assigned: 'primary',
  in_progress: 'primary',
  finished: 'success',
  closed: 'info',
  stopped: 'danger',
}

function statusLabel(status: string) {
  const key = statusLabelKey[status]
  return key ? t(key) : status
}

async function load() {
  loading.value = true
  try {
    const d = await listTasks({
      page: 1,
      size: 5,
      status: 'in_progress',
      filters: { owner_id: auth.user?.id },
    })
    items.value = d.items ?? []
    total.value = d.total ?? 0
  } catch {
    items.value = []
    total.value = 0
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})

const hasItems = computed(() => items.value.length > 0)

function openTask(row: Task) {
  router.push(`/task/tasks/${row.id}`)
}
</script>

<template>
  <WidgetShell :title="t('workbench.widget.myTasks')" :badge="total" :loading="loading">
    <template #actions>
      <el-button link type="primary" size="small" @click="router.push('/task/tasks')">
        {{ t('workbench.viewAll') }}
      </el-button>
    </template>

    <div v-if="!hasItems" class="empty">{{ t('workbench.emptyTasks') }}</div>
    <ul v-else class="task-list">
      <li v-for="it in items" :key="it.id" class="task-item" @click="openTask(it)">
        <span class="task-no">{{ it.taskNo }}</span>
        <span class="task-type">{{ it.taskTypeLabel || '-' }}</span>
        <el-tag :type="tagType[it.status] ?? 'info'" size="small" effect="light" round>
          {{ statusLabel(it.status) }}
        </el-tag>
        <span class="task-time">{{ it.updateTime }}</span>
      </li>
    </ul>
  </WidgetShell>
</template>

<style scoped>
.empty {
  padding: var(--bs-space-5) 0;
  text-align: center;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.task-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.task-item {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  padding: var(--bs-space-2) var(--bs-space-1);
  border-radius: var(--bs-radius-sm);
  cursor: pointer;
  font-size: var(--bs-typography-font-size-sm);
}

.task-item:hover {
  background: var(--bs-color-fill-hover);
}

.task-no {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--bs-color-fg-link);
  font-weight: 500;
}

.task-type {
  flex: none;
  color: var(--bs-color-fg-secondary);
}

.task-time {
  flex: none;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}
</style>
