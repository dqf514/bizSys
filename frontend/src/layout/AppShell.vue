<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import TopBar from './TopBar.vue'
import SideNav from './SideNav.vue'
import TabWorkspace from './TabWorkspace.vue'
import ContextPanel from './ContextPanel.vue'
import CommandPalette from './CommandPalette.vue'
import MobileDock from './MobileDock.vue'
import MobileNavDrawer from './MobileNavDrawer.vue'
import DockSettingsDialog from './DockSettingsDialog.vue'
import { useAuthStore } from '@/stores/auth'
import { useCommandPalette } from '@/composables/useHotkeys'
import { useIsMobile } from '@/composables/useIsMobile'

const auth = useAuthStore()
const { t } = useI18n()
const navCollapsed = ref(localStorage.getItem('bs.navCollapsed') === '1')
const { commandVisible } = useCommandPalette()
const { isMobile } = useIsMobile()

// 移动端：左侧导航改为抽屉
const navDrawerVisible = ref(false)
watch(isMobile, (v) => {
  if (!v) navDrawerVisible.value = false
})

function toggleNav() {
  navCollapsed.value = !navCollapsed.value
  localStorage.setItem('bs.navCollapsed', navCollapsed.value ? '1' : '0')
}

const gridStyle = computed(() => {
  if (isMobile.value) return { gridTemplateColumns: '1fr' }
  return {
    gridTemplateColumns: navCollapsed.value
      ? 'var(--bs-layout-sidenav-collapsed-width) 1fr auto'
      : 'var(--bs-layout-sidenav-width) 1fr auto',
  }
})
</script>

<template>
  <div class="app-shell" :class="{ mobile: isMobile }">
    <header class="shell-top">
      <TopBar @open-command="commandVisible = true" @open-nav="navDrawerVisible = true" />
    </header>
    <div class="shell-body" :style="gridStyle">
      <aside v-if="!isMobile" class="shell-nav">
        <SideNav :collapsed="navCollapsed" @toggle-nav="toggleNav" />
      </aside>
      <main class="shell-main">
        <TabWorkspace />
      </main>
      <ContextPanel />
    </div>
    <footer v-if="!isMobile" class="shell-status">
      <span class="status-item">{{ auth.user?.name || auth.user?.username || '' }}</span>
      <span class="status-item status-env">{{ t('common.shell.env') }}</span>
      <span class="bs-flex-1" />
      <span class="status-item">{{ t('common.shell.menuCount', { count: auth.menus.length }) }}</span>
    </footer>
    <template v-if="isMobile">
      <MobileNavDrawer v-model="navDrawerVisible" />
      <MobileDock />
      <DockSettingsDialog />
    </template>
    <CommandPalette v-model:visible="commandVisible" />
  </div>
</template>

<style scoped>
.app-shell {
  position: fixed;
  inset: 0;
  overflow: hidden;
  display: grid;
  grid-template-rows: var(--bs-layout-topbar-height) 1fr var(--bs-layout-statusbar-height);
  background: var(--bs-color-bg-app);
}

.app-shell.mobile {
  grid-template-rows: var(--bs-layout-topbar-height) 1fr;
}

.shell-top {
  height: var(--bs-layout-topbar-height);
  border-bottom: 1px solid var(--bs-color-border-default);
  background: var(--bs-color-bg-surface);
  overflow: hidden;
}

.shell-body {
  display: grid;
  min-height: 0;
  overflow: hidden;
}

.shell-nav {
  border-right: 1px solid var(--bs-color-border-default);
  background: var(--bs-color-bg-surface);
  overflow: hidden;
  min-width: 0;
}

.shell-main {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.shell-status {
  height: var(--bs-layout-statusbar-height);
  display: flex;
  align-items: center;
  gap: var(--bs-space-3);
  padding: 0 var(--bs-space-3);
  border-top: 1px solid var(--bs-color-border-default);
  background: var(--bs-color-bg-surface);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.status-env {
  padding: 0 var(--bs-space-2);
  border-radius: var(--bs-radius-full);
  background: var(--bs-color-fill-light);
}
</style>
