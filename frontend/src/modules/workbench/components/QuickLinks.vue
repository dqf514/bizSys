<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Document, List, User, Stamp, Money } from '@element-plus/icons-vue'
import WidgetShell from './WidgetShell.vue'
import { useAuthStore } from '@/stores/auth'

defineOptions({ name: 'QuickLinks' })

const { t } = useI18n()
const router = useRouter()
const auth = useAuthStore()

const allLinks = [
  { key: 'contract', labelKey: 'workbench.shortcutContract', path: '/contract/contracts/new', perm: 'contract:create', icon: Document },
  { key: 'task', labelKey: 'workbench.shortcutTask', path: '/task/tasks/new', perm: 'task:create', icon: List },
  { key: 'customer', labelKey: 'workbench.shortcutCustomer', path: '/crm/customers', perm: 'crm:customer:create', icon: User },
  { key: 'approval', labelKey: 'workbench.shortcutApproval', path: '/approval', perm: 'approval:view', icon: Stamp },
  { key: 'settlement', labelKey: 'workbench.shortcutSettlement', path: '/finance/settlements', perm: 'finance:settlement:list', icon: Money },
] as const

const links = computed(() => allLinks.filter((l) => auth.hasPerm(l.perm)))
</script>

<template>
  <WidgetShell :title="t('workbench.widget.quickLinks')">
    <div class="link-grid">
      <button v-for="l in links" :key="l.key" class="link-btn" @click="router.push(l.path)">
        <el-icon class="link-icon"><component :is="l.icon" /></el-icon>
        <span>{{ t(l.labelKey) }}</span>
      </button>
    </div>
    <div v-if="!links.length" class="empty">{{ t('workbench.emptyLinks') }}</div>
  </WidgetShell>
</template>

<style scoped>
.link-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
  gap: var(--bs-space-2);
}

.link-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--bs-space-2);
  padding: var(--bs-space-3) var(--bs-space-2);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-app);
  color: var(--bs-color-fg-default);
  font-size: var(--bs-typography-font-size-sm);
  cursor: pointer;
  transition:
    border-color var(--bs-duration) var(--bs-ease),
    box-shadow var(--bs-duration) var(--bs-ease);
}

.link-btn:hover {
  border-color: var(--bs-color-primary);
  box-shadow: var(--bs-shadow-elevation1);
}

.link-icon {
  font-size: 20px;
  color: var(--bs-color-primary);
}

.empty {
  padding: var(--bs-space-4) 0;
  text-align: center;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}
</style>
