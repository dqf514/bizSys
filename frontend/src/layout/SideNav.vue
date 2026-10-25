<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElIcon, ElMenu, ElPopover } from 'element-plus'
import { Expand, Fold, Setting } from '@element-plus/icons-vue'
import SideNavItem from './SideNavItem.vue'
import NavSortDialog from './NavSortDialog.vue'
import { useNavZones } from './useNavZones'
import type { MenuNode } from '@/api/types'

const props = defineProps<{ collapsed: boolean }>()
const emit = defineEmits<{ (e: 'toggle-nav'): void }>()

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const active = computed(() => route.path)

const { topMenus, zones, systemZone, customOrder, validOrder, navZoneDirs, menuTitle, persistOrder } = useNavZones()

// 失效的个人排序一次性静默重置（避免旧 id 永久卡住默认结构）
const staleResetDone = ref(false)
watch(
  [customOrder, validOrder],
  ([order, valid]) => {
    if (staleResetDone.value || !order.length || valid.length || !navZoneDirs.value.length) return
    staleResetDone.value = true
    void persistOrder('')
  },
  { immediate: true },
)

// ---- 底部工具栏：系统管理入口（向上弹层） + 折叠切换 ----
const sysVisible = ref(false)

function gotoSystemItem(node: MenuNode) {
  if (!node.path) return
  sysVisible.value = false
  router.push(node.path)
}

/** 系统管理弹层内当前路由高亮 */
function isActivePath(node: MenuNode) {
  return Boolean(node.path) && route.path === node.path
}
</script>

<template>
  <div class="side-nav" :class="{ collapsed: props.collapsed }">
    <ElMenu
      :default-active="active"
      :collapse="props.collapsed"
      :collapse-transition="false"
      class="nav-menu"
      router
    >
      <SideNavItem v-for="node in topMenus" :key="node.id" :node="node" :collapsed="props.collapsed" />
      <div v-for="zone in zones" :key="zone.id" class="nav-zone">
        <div class="nav-zone-title">{{ menuTitle(zone) }}</div>
        <SideNavItem v-for="child in zone.children" :key="child.id" :node="child" :collapsed="props.collapsed" />
      </div>
    </ElMenu>
    <div class="nav-footer">
      <ElPopover
        v-if="systemZone"
        v-model:visible="sysVisible"
        trigger="click"
        placement="top-start"
        :width="300"
        popper-class="nav-system-pop"
      >
        <template #reference>
          <button
            type="button"
            class="nav-system-btn"
            :title="menuTitle(systemZone)"
          >
            <ElIcon><Setting /></ElIcon>
            <span class="nav-label">{{ menuTitle(systemZone) }}</span>
          </button>
        </template>

        <div class="system-panel">
          <div v-for="group in systemZone.children" :key="group.id" class="system-group">
            <div class="system-group-title">{{ menuTitle(group) }}</div>
            <button
              v-for="item in group.children"
              :key="item.id"
              type="button"
              class="panel-item"
              :class="{ active: isActivePath(item) }"
              @click="gotoSystemItem(item)"
            >
              <span>{{ menuTitle(item) }}</span>
            </button>
          </div>
        </div>
      </ElPopover>

      <button
        type="button"
        class="nav-fold-btn"
        :title="props.collapsed ? t('common.action.expand') : t('common.action.collapse')"
        @click="emit('toggle-nav')"
      >
        <ElIcon>
          <Expand v-if="props.collapsed" />
          <Fold v-else />
        </ElIcon>
      </button>
    </div>

    <NavSortDialog />
  </div>
</template>

<style scoped>
.side-nav {
  height: 100%;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.nav-menu {
  border-right: none;
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  background: transparent;
}

.nav-zone {
  border-top: 1px solid var(--bs-color-border-subtle);
  margin-top: var(--bs-space-1);
  padding-top: var(--bs-space-1);
}

.nav-zone-title {
  padding: var(--bs-space-1) var(--bs-space-4) var(--bs-space-1) calc(var(--bs-space-4) + 4px);
  font-size: var(--bs-typography-font-size-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--bs-color-fg-muted);
  user-select: none;
}

/* 折叠态：全导航零文字（区标题 + 菜单项文字 + 底部入口文字全部隐藏，仅留图标） */
.side-nav.collapsed .nav-zone-title,
.side-nav.collapsed .nav-label,
.side-nav.collapsed :deep(.nav-label) {
  display: none;
}

.nav-footer {
  flex: none;
  display: flex;
  align-items: center;
  gap: var(--bs-space-1);
  border-top: 1px solid var(--bs-color-border-default);
  padding: var(--bs-space-1);
}

.nav-system-btn {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 6px;
  height: var(--bs-density-nav-item-height);
  padding: 0 var(--bs-space-2);
  border: none;
  border-radius: var(--bs-radius-md);
  background: transparent;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
  cursor: pointer;
}

.side-nav.collapsed .nav-system-btn {
  justify-content: center;
  padding: 0;
}

.nav-system-btn:hover {
  background: var(--bs-color-fill-light);
  color: var(--bs-color-primary);
}

.nav-fold-btn {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: var(--bs-density-nav-item-height);
  border: none;
  border-radius: var(--bs-radius-md);
  background: transparent;
  color: var(--bs-color-fg-muted);
  cursor: pointer;
}

.nav-fold-btn:hover {
  background: var(--bs-color-fill-light);
  color: var(--bs-color-primary);
}

.system-panel {
  display: flex;
  flex-direction: column;
  max-height: 60vh;
  overflow-y: auto;
}

.system-group + .system-group {
  margin-top: var(--bs-space-1);
  border-top: 1px solid var(--bs-color-border-subtle);
  padding-top: var(--bs-space-1);
}

.system-group-title {
  padding: var(--bs-space-1) var(--bs-space-2);
  font-size: var(--bs-typography-font-size-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--bs-color-fg-muted);
  user-select: none;
}

.panel-item {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  width: 100%;
  padding: var(--bs-space-2);
  border: none;
  border-radius: var(--bs-radius-sm);
  background: transparent;
  color: var(--bs-color-fg-default);
  font-size: var(--bs-typography-font-size-sm);
  cursor: pointer;
  text-align: left;
}

.panel-item:hover {
  background: var(--bs-color-fill-hover);
}

.panel-item.active {
  color: var(--bs-color-primary);
  background: var(--bs-color-brand-primary-soft);
}

:deep(.el-menu-item),
:deep(.el-sub-menu__title) {
  height: var(--bs-density-nav-item-height);
  line-height: var(--bs-density-nav-item-height);
}

:deep(.el-menu-item.is-active) {
  background: var(--bs-color-brand-primary-soft);
  color: var(--bs-color-primary);
}
</style>
