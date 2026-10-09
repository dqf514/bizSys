<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { listApprovalTasks } from '@/api/approval'
import { listTasks, taskCounts } from '@/api/task'
import { listContracts } from '@/api/contract'
import { listCustomers } from '@/api/crm'

defineOptions({ name: 'Dashboard' })

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()

const stats = ref({
  approvalTodo: 0,
  myTasks: 0,
  contractApproving: 0,
  customerTotal: 0,
  taskTotal: 0,
})
const loading = ref(false)

async function loadStats() {
  loading.value = true
  const safe = async (fn: () => Promise<number>) => {
    try {
      return await fn()
    } catch {
      return 0
    }
  }
  stats.value = {
    approvalTodo: await safe(async () => {
      const d = await listApprovalTasks('todo', { page: 1, size: 1 })
      return d.total ?? 0
    }),
    myTasks: await safe(async () => {
      const d = await listTasks({ page: 1, size: 1 })
      return d.total ?? 0
    }),
    contractApproving: await safe(async () => {
      const d = await listContracts({ page: 1, size: 1, status: 'approving' })
      return d.total ?? 0
    }),
    customerTotal: await safe(async () => {
      const d = await listCustomers({ page: 1, size: 1, status: 'all' })
      return d.total ?? 0
    }),
    taskTotal: await safe(async () => {
      try {
        const c = await taskCounts()
        return Object.values(c ?? {}).reduce((a, b) => a + Number(b || 0), 0)
      } catch {
        const d = await listTasks({ page: 1, size: 1 })
        return d.total ?? 0
      }
    }),
  }
  loading.value = false
}

onMounted(() => {
  void loadStats()
})

const cards = [
  { key: 'approvalTodo', labelKey: 'workbench.card.approvalTodo', path: '/approval', color: 'var(--bs-color-semantic-warning)' },
  { key: 'myTasks', labelKey: 'workbench.card.myTasks', path: '/task/tasks', color: 'var(--bs-color-primary)' },
  { key: 'contractApproving', labelKey: 'workbench.card.contractApproving', path: '/contract/contracts', color: 'var(--bs-color-semantic-info)' },
  { key: 'customerTotal', labelKey: 'workbench.card.customerTotal', path: '/crm/customers', color: 'var(--bs-color-semantic-success)' },
  { key: 'taskTotal', labelKey: 'workbench.card.taskTotal', path: '/task/tasks', color: 'var(--bs-color-semantic-danger)' },
] as const

const shortcuts = [
  { labelKey: 'workbench.shortcutCustomer', path: '/crm/customers' },
  { labelKey: 'workbench.shortcutContract', path: '/contract/contracts/new' },
  { labelKey: 'workbench.shortcutTask', path: '/task/tasks/new' },
  { labelKey: 'workbench.shortcutApproval', path: '/approval' },
] as const
</script>

<template>
  <div class="dashboard" v-loading="loading">
    <div class="welcome">
      <h2 class="welcome-title">{{ t('workbench.welcome', { name: auth.user?.name || auth.user?.username || '' }) }}</h2>
      <p class="welcome-sub">{{ t('workbench.title') }}</p>
    </div>

    <div class="stat-grid">
      <div v-for="card in cards" :key="card.key" class="stat-card" @click="router.push(card.path)">
        <div class="stat-label">{{ t(card.labelKey) }}</div>
        <div class="stat-value" :style="{ color: card.color }">
          {{ (stats as Record<string, number>)[card.key] ?? 0 }}
        </div>
      </div>
    </div>

    <div class="section">
      <div class="section-title">{{ t('workbench.shortcut') }}</div>
      <div class="shortcut-grid">
        <el-button
          v-for="s in shortcuts"
          :key="s.path"
          class="shortcut-btn"
          @click="router.push(s.path)"
        >
          {{ t(s.labelKey) }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.dashboard {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-4);
  padding: var(--bs-space-5);
  height: 100%;
  overflow: auto;
}

.welcome-title {
  font-size: var(--bs-typography-font-size-xl);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.welcome-sub {
  margin-top: 4px;
  color: var(--bs-color-fg-muted);
}

.stat-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: var(--bs-space-3);
}

.stat-card {
  padding: var(--bs-space-4);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  cursor: pointer;
  transition: box-shadow var(--bs-duration) var(--bs-ease);
}

.stat-card:hover {
  box-shadow: var(--bs-shadow-elevation2);
}

.stat-label {
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-secondary);
}

.stat-value {
  margin-top: var(--bs-space-2);
  font-size: var(--bs-typography-font-size-xxl);
  font-weight: 700;
}

.section-title {
  margin-bottom: var(--bs-space-2);
  font-size: var(--bs-typography-font-size-md);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.shortcut-grid {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bs-space-2);
}
</style>
