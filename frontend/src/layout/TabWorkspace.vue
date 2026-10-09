<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useTabsStore } from '@/stores/tabs'
import type { TabItem } from '@/stores/tabs'

const route = useRoute()
const router = useRouter()
const tabsStore = useTabsStore()
const { t } = useI18n()

const menuVisible = ref(false)
const menuPos = ref({ x: 0, y: 0 })
const menuTab = ref<TabItem | null>(null)

const includeNames = computed(() =>
  tabsStore.tabs.filter((tab) => tab.keepAlive && tab.componentName).map((tab) => tab.componentName as string),
)

function tabLabel(tab: TabItem) {
  return tab.titleKey ? t(tab.titleKey) : tab.title
}

function activate(tab: TabItem) {
  tabsStore.setActive(tab.key)
  if (route.path !== tab.path) {
    router.push(tab.fullPath || tab.path)
  }
}

function closeTab(tab: TabItem) {
  const shouldNavigate = tabsStore.close(tab.key, true)
  if (shouldNavigate) {
    const next = tabsStore.tabs.find((x) => x.key === tabsStore.active) ?? tabsStore.tabs[0]
    if (next) {
      router.push(next.fullPath || next.path)
    } else {
      router.push('/workbench')
    }
  }
}

function onContextmenu(e: MouseEvent, tab: TabItem) {
  e.preventDefault()
  menuTab.value = tab
  menuPos.value = { x: e.clientX, y: e.clientY }
  menuVisible.value = true
}

function onDblClick(tab: TabItem) {
  tabsStore.togglePin(tab.key)
}

function ctx(action: 'close' | 'closeOthers' | 'closeRight' | 'pin' | 'refresh') {
  const tab = menuTab.value
  if (!tab) return
  menuVisible.value = false
  if (action === 'close') closeTab(tab)
  else if (action === 'closeOthers') {
    tabsStore.closeOthers(tab.key)
    activate(tab)
  } else if (action === 'closeRight') {
    tabsStore.closeRight(tab.key)
  } else if (action === 'pin') {
    tabsStore.togglePin(tab.key)
  } else if (action === 'refresh') {
    router.replace({ path: '/redirect' + tab.path }).catch(() => {
      // fallback: re-push
      router.push(tab.fullPath || tab.path)
    })
  }
}

// scroll restore for list pages
const scrollRef = ref<HTMLElement>()

function rememberScroll() {
  const el = scrollRef.value
  if (!el) return
  tabsStore.updateScroll(route.path, el.scrollTop)
}

onMounted(() => {
  document.addEventListener('click', () => {
    menuVisible.value = false
  })
  nextTick(() => {
    const el = scrollRef.value
    if (el) el.scrollTop = tabsStore.getScroll(route.path)
  })
})

watch(
  () => route.path,
  () => {
    nextTick(() => {
      const el = scrollRef.value
      if (el) el.scrollTop = tabsStore.getScroll(route.path)
    })
  },
)
</script>

<template>
  <div class="tab-workspace" @contextmenu.self.prevent>
    <div class="tab-bar">
      <div class="tab-list">
        <div
          v-for="tab in tabsStore.tabs"
          :key="tab.key"
          class="tab-item"
          :class="{ active: tab.key === tabsStore.active, pinned: tab.pinned }"
          @click="activate(tab)"
          @dblclick="onDblClick(tab)"
          @contextmenu="onContextmenu($event, tab)"
        >
          <span v-if="tab.pinned" class="pin-dot" />
          <span class="tab-title">{{ tabLabel(tab) }}</span>
          <button
            v-if="!tab.pinned"
            class="tab-close"
            type="button"
            :title="t('common.tab.close')"
            @click.stop="closeTab(tab)"
          >
            ×
          </button>
        </div>
      </div>
    </div>

    <div ref="scrollRef" class="tab-content" @scroll.passive="rememberScroll">
      <router-view v-slot="{ Component }">
        <KeepAlive :include="includeNames">
          <component :is="Component" :key="route.path" />
        </KeepAlive>
      </router-view>
    </div>

    <teleport to="body">
      <div
        v-if="menuVisible"
        class="tab-ctx-menu"
        :style="{ left: menuPos.x + 'px', top: menuPos.y + 'px' }"
        @click.stop
      >
        <div class="ctx-item" @click="ctx('close')">{{ t('common.tab.close') }}</div>
        <div class="ctx-item" @click="ctx('closeOthers')">{{ t('common.tab.closeOthers') }}</div>
        <div class="ctx-item" @click="ctx('closeRight')">{{ t('common.tab.closeRight') }}</div>
        <div class="ctx-item" @click="ctx('pin')">
          {{ menuTab?.pinned ? t('common.tab.unpin') : t('common.tab.pin') }}
        </div>
        <div class="ctx-item" @click="ctx('refresh')">{{ t('common.tab.refresh') }}</div>
      </div>
    </teleport>
  </div>
</template>

<style scoped>
.tab-workspace {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
}

.tab-bar {
  height: var(--bs-layout-tabbar-height);
  flex-shrink: 0;
  border-bottom: 1px solid var(--bs-color-border-default);
  background: var(--bs-color-bg-surface);
  overflow: hidden;
}

.tab-list {
  display: flex;
  align-items: stretch;
  height: 100%;
  overflow-x: auto;
  overflow-y: hidden;
}

.tab-list::-webkit-scrollbar {
  height: 0;
}

.tab-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 100%;
  max-width: 200px;
  padding: 0 var(--bs-space-3);
  border-right: 1px solid var(--bs-color-border-subtle);
  background: var(--bs-color-bg-surface);
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
  cursor: pointer;
  user-select: none;
  white-space: nowrap;
}

.tab-item.active {
  background: var(--bs-color-bg-app);
  color: var(--bs-color-primary);
  box-shadow: inset 0 2px 0 var(--bs-color-primary);
}

.tab-item.pinned .tab-title {
  font-weight: 600;
}

.pin-dot {
  width: 6px;
  height: 6px;
  border-radius: var(--bs-radius-full);
  background: var(--bs-color-primary);
}

.tab-title {
  overflow: hidden;
  text-overflow: ellipsis;
}

.tab-close {
  width: 16px;
  height: 16px;
  border: none;
  border-radius: var(--bs-radius-full);
  background: transparent;
  color: var(--bs-color-fg-muted);
  font-size: 12px;
  line-height: 1;
  cursor: pointer;
}

.tab-close:hover {
  background: var(--bs-color-fill-dark);
  color: var(--bs-color-fg-default);
}

.tab-content {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: var(--bs-color-bg-app);
}

.tab-ctx-menu {
  position: fixed;
  z-index: 3000;
  min-width: 140px;
  padding: 4px;
  border: 1px solid var(--bs-color-border-default);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-elevated);
  box-shadow: var(--bs-shadow-elevation3);
}

.ctx-item {
  padding: 6px 10px;
  border-radius: var(--bs-radius-sm);
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-default);
  cursor: pointer;
}

.ctx-item:hover {
  background: var(--bs-color-fill-hover);
}
</style>
