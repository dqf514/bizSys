<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import TaskDetailPanel from '../components/TaskDetailPanel.vue'
import BackButton from '@/components/common/BackButton.vue'
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
  <div class="bs-page bs-page--scroll">
    <div class="bs-page-header">
      <h2 class="detail-title">{{ loaded?.taskName || t('task.task.detail') }}</h2>
      <BackButton to="/task/tasks" />
    </div>
    <div class="bs-page-card">
      <TaskDetailPanel :task-id="taskId" @loaded="loaded = $event" @removed="onRemoved" />
    </div>
  </div>
</template>

<style scoped>
.detail-title {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  margin: 0;
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
}
</style>
