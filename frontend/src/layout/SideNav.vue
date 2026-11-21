<script setup lang="ts">
import { computed, h, ref, resolveComponent, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElIcon, ElMenu, ElPopover } from 'element-plus'
import { ArrowRight, Expand, Fold, Setting } from '@element-plus/icons-vue'
import SideNavItem from './SideNavItem.vue'
import NavSortDialog from './NavSortDialog.vue'
import { countZoneItems, useNavZones } from './useNavZones'
import { usePopoverA11y } from '@/composables/usePopoverA11y'
import type { MenuNode } from '@/api/types'

const props = defineProps<{ collapsed: boolean }>()
const emit = defineEmits<{ (e: 'toggle-nav'): void }>()

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const active = computed(() => route.path)

const {
  topMenus,
  zones,
  systemZone,
  customOrder,
  validOrder,
  navZoneDirs,
  menuTitle,
  persistOrder,
  toggleZone,
  isZoneOpen,
  isZoneActive,
} = useNavZones()

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

function renderIcon(icon?: string) {
  if (!icon) return null
  const comp = resolveComponent(icon)
  if (!comp) return null
  return h(ElIcon, null, { default: () => h(comp as never) })
}

/* ---------- 展开态：分区手风琴 ---------- */

/** 分区头按钮的无障碍描述：分区名 + 展开/收起动作 */
function zoneToggleLabel(zone: MenuNode) {
  const action = isZoneOpen(zone) ? t('common.nav.collapseZone') : t('common.nav.expandZone')
  return `${menuTitle(zone)} - ${action}`
}

/* ---------- 折叠态：图标轨 + 浮层 ---------- */

interface FlyoutEntry {
  key: string
  kind: 'group' | 'item'
  title: string
  node?: MenuNode
}

/** 收集节点下的全部可见叶子菜单（递归 dir） */
function collectLeaves(node: MenuNode, out: MenuNode[] = []): MenuNode[] {
  for (const c of node.children ?? []) {
    if (c.visible === 0) continue
    if (c.menuType === 'menu') out.push(c)
    else if (c.menuType === 'dir') collectLeaves(c, out)
  }
  return out
}

/** 浮层条目：二级目录作为分组标题，叶子菜单作为条目 */
function flyoutEntries(zone: MenuNode): FlyoutEntry[] {
  const out: FlyoutEntry[] = []
  for (const child of zone.children ?? []) {
    if (child.visible === 0) continue
    if (child.menuType === 'dir') {
      const leaves = collectLeaves(child)
      if (!leaves.length) continue
      out.push({ key: `g-${child.id}`, kind: 'group', title: menuTitle(child) })
      for (const leaf of leaves) {
        out.push({ key: `i-${leaf.id}`, kind: 'item', title: menuTitle(leaf), node: leaf })
      }
    } else if (child.menuType === 'menu') {
      out.push({ key: `i-${child.id}`, kind: 'item', title: menuTitle(child), node: child })
    }
  }
  return out
}

/** 当前打开的浮层分区（一次只开一个） */
const flyoutZoneId = ref<number | null>(null)

function onFlyoutVisible(zone: MenuNode, v: boolean) {
  if (v) flyoutZoneId.value = zone.id
  else if (flyoutZoneId.value === zone.id) flyoutZoneId.value = null
}

function openFlyout(zone: MenuNode) {
  if (flyoutZoneId.value !== zone.id) flyoutZoneId.value = zone.id
}

function closeFlyout() {
  flyoutZoneId.value = null
}

function gotoNode(node: MenuNode) {
  if (!node.path) return
  closeFlyout()
  router.push(node.path)
}

/* ---------- 底部工具栏：系统管理入口（向上弹层） + 折叠切换 ---------- */
const sysVisible = ref(false)
const sysBtnRef = ref<HTMLButtonElement>()
usePopoverA11y(sysVisible, 'nav-system-pop', sysBtnRef, { arrowNav: true })

function gotoSystemItem(node: MenuNode) {
  if (!node.path) return
  sysVisible.value = false
  router.push(node.path)
}

/** 弹层内当前路由高亮（详情页按路径前缀命中） */
function isActivePath(node: MenuNode) {
  if (!node.path) return false
  return route.path === node.path || route.path.startsWith(`${node.path}/`)
}
</script>

<template>
  <div class="side-nav" :class="{ collapsed: props.collapsed }">
    <!-- 展开态：工作台 + 分区手风琴 -->
    <ElMenu v-if="!props.collapsed" :default-active="active" class="nav-menu" router>
      <SideNavItem v-for="node in topMenus" :key="node.id" :node="node" />
      <div
        v-for="zone in zones"
        :key="zone.id"
        class="nav-zone"
        :class="{ open: isZoneOpen(zone), active: isZoneActive(zone) }"
      >
        <button
          type="button"
          class="nav-zone-title"
          :aria-expanded="isZoneOpen(zone)"
          :aria-label="zoneToggleLabel(zone)"
          @click="toggleZone(zone)"
        >
          <ElIcon class="nav-zone-caret"><ArrowRight /></ElIcon>
          <span class="nav-zone-name">{{ menuTitle(zone) }}</span>
          <span class="nav-zone-count">{{ countZoneItems(zone) }}</span>
        </button>
        <div v-show="isZoneOpen(zone)" class="nav-zone-body">
          <SideNavItem v-for="child in zone.children" :key="child.id" :node="child" />
        </div>
      </div>
    </ElMenu>

    <!-- 折叠态：图标轨（工作台 + 各分区），悬停/聚焦弹出分区浮层 -->
    <div v-else class="nav-rail">
      <button
        v-for="node in topMenus"
        :key="node.id"
        type="button"
        class="rail-btn"
        :class="{ active: isActivePath(node) }"
        :title="menuTitle(node)"
        :aria-label="menuTitle(node)"
        @click="gotoNode(node)"
      >
        <component :is="renderIcon(node.icon)" v-if="node.icon" />
      </button>

      <ElPopover
        v-for="zone in zones"
        :key="zone.id"
        :visible="flyoutZoneId === zone.id"
        trigger="hover"
        placement="right-start"
        :width="260"
        popper-class="nav-zone-flyout"
        @update:visible="(v: boolean) => onFlyoutVisible(zone, v)"
      >
        <template #reference>
          <button
            type="button"
            class="rail-btn"
            :class="{ active: isZoneActive(zone) }"
            :title="menuTitle(zone)"
            :aria-label="menuTitle(zone)"
            :aria-expanded="flyoutZoneId === zone.id"
            @click="openFlyout(zone)"
            @keydown.esc="closeFlyout()"
          >
            <component :is="renderIcon(zone.icon)" v-if="zone.icon" />
          </button>
        </template>

        <div class="zone-panel" role="menu" :aria-label="menuTitle(zone)">
          <div class="zone-panel-title">{{ menuTitle(zone) }}</div>
          <template v-for="entry in flyoutEntries(zone)" :key="entry.key">
            <div v-if="entry.kind === 'group'" class="zone-group-title">{{ entry.title }}</div>
            <button
              v-else
              type="button"
              role="menuitem"
              class="zone-item"
              :class="{ active: entry.node && isActivePath(entry.node) }"
              @click="entry.node && gotoNode(entry.node)"
            >
              <span>{{ entry.title }}</span>
            </button>
          </template>
        </div>
      </ElPopover>
    </div>

    <div class="nav-footer">
      <ElPopover
        v-if="systemZone"
        v-model:visible="sysVisible"
        trigger="click"
        :placement="props.collapsed ? 'right-start' : 'top-start'"
        :width="300"
        popper-class="nav-system-pop"
        role="menu"
      >
        <template #reference>
          <button
            ref="sysBtnRef"
            type="button"
            class="nav-system-btn"
            :title="menuTitle(systemZone)"
            :aria-label="menuTitle(systemZone)"
          >
            <ElIcon><Setting /></ElIcon>
            <span class="nav-label">{{ menuTitle(systemZone) }}</span>
          </button>
        </template>

        <div class="system-panel" role="menu" :aria-label="menuTitle(systemZone)">
          <div v-for="group in systemZone.children" :key="group.id" class="system-group">
            <div class="system-group-title">{{ menuTitle(group) }}</div>
            <button
              v-for="item in group.children"
              :key="item.id"
              type="button"
              role="menuitem"
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
        :aria-label="props.collapsed ? t('common.action.expand') : t('common.action.collapse')"
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
  display: flex;
  align-items: center;
  gap: var(--bs-space-1);
  width: 100%;
  padding: var(--bs-space-1) var(--bs-space-3);
  border: none;
  border-radius: var(--bs-radius-sm);
  background: transparent;
  font-size: var(--bs-typography-font-size-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--bs-color-fg-muted);
  cursor: pointer;
  text-align: left;
}

.nav-zone-title:hover {
  background: var(--bs-color-fill-light);
  color: var(--bs-color-fg-default);
}

.nav-zone.active > .nav-zone-title {
  color: var(--bs-color-primary);
}

.nav-zone-caret {
  transition: transform var(--bs-motion-fast) var(--bs-motion-curve);
}

.nav-zone.open .nav-zone-caret {
  transform: rotate(90deg);
}

.nav-zone-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav-zone-count {
  flex: none;
  font-weight: 400;
  letter-spacing: 0;
  color: var(--bs-color-fg-muted);
  opacity: 0.8;
}

/* 折叠态：全导航零文字（底部入口文字隐藏，仅留图标） */
.side-nav.collapsed .nav-label,
.side-nav.collapsed :deep(.nav-label) {
  display: none;
}

/* 折叠态图标轨 */
.nav-rail {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--bs-space-1);
  padding: var(--bs-space-2) 0;
}

.rail-btn {
  flex: none;
  width: 40px;
  height: 40px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: var(--bs-radius-md);
  background: transparent;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-lg);
  cursor: pointer;
}

.rail-btn:hover {
  background: var(--bs-color-fill-light);
  color: var(--bs-color-primary);
}

.rail-btn.active {
  background: var(--bs-color-brand-primary-soft);
  color: var(--bs-color-primary);
}

/* 分区浮层面板 */
.zone-panel {
  display: flex;
  flex-direction: column;
  max-height: 70vh;
  overflow-y: auto;
}

.zone-panel-title {
  padding: var(--bs-space-1) var(--bs-space-2);
  font-size: var(--bs-typography-font-size-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--bs-color-fg-muted);
  user-select: none;
}

.zone-group-title {
  padding: var(--bs-space-1) var(--bs-space-2) 2px;
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  user-select: none;
}

.zone-item {
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

.zone-item:hover {
  background: var(--bs-color-fill-hover);
}

.zone-item.active {
  color: var(--bs-color-primary);
  background: var(--bs-color-brand-primary-soft);
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
