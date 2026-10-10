<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import TaskDetailPanel from '../components/TaskDetailPanel.vue'
import type { Task } from '@/api/types'

defineOptions({ name: 'TaskDetail' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()

const taskId = computed(() => Number(route.params.id) || 0)
const loaded = ref<Task | null>(null)

function onRemoved() {
  router.push('/task/tasks')
}
</script>

<template>
  <div class="task-detail">
    <div class="detail-header">
      <h2 class="detail-title">{{ loaded?.taskName || t('task.task.detail') }}</h2>
      <el-button @click="router.push('/task/tasks')">{{ t('common.action.back') }}</el-button>
    </div>
    <TaskDetailPanel :task-id="taskId" @loaded="loaded = $event" @removed="onRemoved" />
  </div>
</template>

<style scoped>
.task-detail {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
  padding: var(--bs-space-4);
  height: 100%;
  overflow: auto;
  background: var(--bs-color-bg-surface);
}

.detail-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.detail-title {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
}
</style>
