<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'

defineOptions({ name: 'PortalMobileDock' })

const props = defineProps<{
  scopes: string[]
  loggedIn: boolean
}>()

const { t } = useI18n()
const route = useRoute()

interface DockItem {
  to: string
  labelKey: string
  icon: string
}

const items = computed<DockItem[]>(() => {
  const list: DockItem[] = [
    { to: '/portal', labelKey: 'portal.portal.dock.home', icon: 'Grid' },
    { to: '/portal/tenders', labelKey: 'portal.portal.dock.tender', icon: 'Tickets' },
  ]
  if (props.loggedIn) {
    if (props.scopes.includes('visit')) {
      list.push({ to: '/portal/visits', labelKey: 'portal.portal.dock.visit', icon: 'Position' })
    }
    list.push({ to: '/portal/my', labelKey: 'portal.portal.dock.my', icon: 'User' })
  }
  return list
})

const isActive = (to: string) =>
  to === '/portal' ? route.path === '/portal' : route.path.startsWith(to)
</script>

<template>
  <nav class="portal-dock" :aria-label="t('portal.portal.dock.title')">
    <router-link
      v-for="item in items"
      :key="item.to"
      :to="item.to"
      class="portal-dock-item"
      :class="{ active: isActive(item.to) }"
    >
      <el-icon class="portal-dock-icon"><component :is="item.icon" /></el-icon>
      <span class="portal-dock-label">{{ t(item.labelKey) }}</span>
    </router-link>
  </nav>
</template>

<style scoped>
.portal-dock {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 30;
  display: flex;
  align-items: stretch;
  height: calc(var(--bs-layout-portal-bottom-nav-height) + env(safe-area-inset-bottom));
  padding-bottom: env(safe-area-inset-bottom);
  background: var(--bs-color-bg-surface);
  border-top: 1px solid var(--bs-color-border-subtle);
  box-shadow: var(--bs-shadow-elevation1);
}

.portal-dock-item {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  text-decoration: none;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
  /* 触控热区不小于 44px */
  min-height: 44px;
}

.portal-dock-item.active {
  color: var(--bs-color-primary);
}

.portal-dock-icon {
  font-size: 20px;
}

.portal-dock-label {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
}
</style>
