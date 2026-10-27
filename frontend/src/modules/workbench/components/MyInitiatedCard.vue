<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import WidgetShell from './WidgetShell.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { listApprovalTasks } from '@/api/approval'
import type { ApprovalTask } from '@/api/types'

defineOptions({ name: 'MyInitiatedCard' })

const { t } = useI18n()
const router = useRouter()

const items = ref<ApprovalTask[]>([])
const total = ref(0)
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const d = await listApprovalTasks('initiated', { page: 1, size: 5 })
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

function bizTypeLabel(bt: string) {
  if (bt === 'contract') return t('approval.approval.bizContract')
  if (bt === 'task') return t('approval.approval.bizTask')
  if (bt === 'tender_award') return t('approval.approval.bizTenderAward')
  return bt
}

function goCenter() {
  router.push('/approval')
}
</script>

<template>
  <WidgetShell :title="t('workbench.widget.myInitiated')" :badge="total" :loading="loading">
    <template #actions>
      <el-button link type="primary" size="small" @click="goCenter">{{ t('workbench.viewAll') }}</el-button>
    </template>

    <div v-if="!items.length" class="empty">{{ t('workbench.emptyInitiated') }}</div>
    <ul v-else class="todo-list">
      <li v-for="it in items" :key="it.id" class="todo-item" @click="goCenter">
        <span class="todo-biz">{{ bizTypeLabel(it.bizType) }}</span>
        <span class="todo-title" :title="it.title">{{ it.title }}</span>
        <StatusTag :status="String(it.status)" i18n-prefix="approval.approval.status" />
        <span v-if="it.unreadCount" class="unread-chip">{{ it.unreadCount > 99 ? '99+' : it.unreadCount }}</span>
        <span class="todo-time">{{ it.createTime }}</span>
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

.todo-list {
  margin: 0;
  padding: 0;
  list-style: none;
}

.todo-item {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  padding: var(--bs-space-2) var(--bs-space-1);
  border-radius: var(--bs-radius-sm);
  cursor: pointer;
  font-size: var(--bs-typography-font-size-sm);
}

.todo-item:hover {
  background: var(--bs-color-fill-hover);
}

.todo-biz {
  flex: none;
  padding: 0 var(--bs-space-1);
  border-radius: var(--bs-radius-sm);
  background: var(--bs-color-semantic-warning-soft);
  color: var(--bs-color-semantic-warning);
  font-size: var(--bs-typography-font-size-xs);
}

.todo-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--bs-color-fg-default);
}

.unread-chip {
  flex: none;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  background: var(--bs-color-semantic-danger);
  color: var(--bs-color-fg-inverse);
  font-size: var(--bs-typography-font-size-xs);
  line-height: 16px;
  text-align: center;
}

.todo-time {
  flex: none;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}
</style>
