<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElButton, ElDialog, ElIcon, ElMenu, ElMessage } from 'element-plus'
import { Operation, Rank } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import * as authApi from '@/api/auth'
import type { MenuNode } from '@/api/types'
import SideNavItem from './SideNavItem.vue'

const props = defineProps<{ collapsed: boolean }>()

const route = useRoute()
const auth = useAuthStore()
const { t } = useI18n()

const active = computed(() => route.path)

function visibleMenus(nodes: MenuNode[]): MenuNode[] {
  return nodes
    .filter((n) => n.visible !== 0 && (n.menuType === 'dir' || n.menuType === 'menu'))
    .map((n) => ({ ...n, children: visibleMenus(n.children ?? []) }))
    .filter((n) => n.menuType === 'menu' || (n.children?.length ?? 0) > 0)
    .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0))
}

function menuTitle(node: MenuNode) {
  return node.titleKey ? t(node.titleKey) : node.name
}

// ---- 三区结构：顶层独立菜单（工作台）钉在顶部，顶级目录渲染为「区」 ----
const visibleTree = computed(() => visibleMenus(auth.menus))
/** 顶层独立菜单（工作台），不属于任何区，固定最前 */
const topMenus = computed(() => visibleTree.value.filter((n) => n.menuType === 'menu'))
/** 顶级目录 = 区（业务系统/OA系统/系统管理）；无权限区已被 visibleMenus 整区剔除 */
const zoneDirs = computed(() => visibleTree.value.filter((n) => n.menuType === 'dir'))

/** per-user zone order stored as CSV of menu ids in prefs.navOrder */
const customOrder = computed<number[]>(() => {
  const raw = auth.user?.prefs?.navOrder
  if (typeof raw !== 'string' || !raw) return []
  return raw
    .split(',')
    .map((s) => Number(s))
    .filter((n) => Number.isFinite(n))
})

/**
 * 结构优先：navOrder 是批次A之前的旧数据（含已移动/已删除的顶层业务菜单 id）
 * 或与当前区结构不一致（缺区/多 id）时整体作废，回退默认区序。
 */
const validOrder = computed<number[]>(() => {
  const order = customOrder.value
  if (!order.length) return []
  const ids = new Set(zoneDirs.value.map((n) => n.id))
  if (order.length !== ids.size || order.some((id) => !ids.has(id))) return []
  return order
})

const zones = computed(() => {
  const order = validOrder.value
  if (!order.length) return zoneDirs.value
  const rank = new Map(order.map((id, i) => [id, i]))
  return [...zoneDirs.value].sort((a, b) => (rank.get(a.id) ?? 0) - (rank.get(b.id) ?? 0))
})

async function persistOrder(csv: string) {
  await authApi.updatePrefs({ navOrder: csv })
  if (auth.user) auth.user.prefs = { ...(auth.user.prefs ?? {}), navOrder: csv }
}

// 失效的个人排序一次性静默重置（避免旧 id 永久卡住默认结构）
const staleResetDone = ref(false)
watch(
  [customOrder, validOrder],
  ([order, valid]) => {
    if (staleResetDone.value || !order.length || valid.length || !zoneDirs.value.length) return
    staleResetDone.value = true
    void persistOrder('')
  },
  { immediate: true },
)

// ---- customize dialog（区级排序；工作台固定顶部不参与） ----
const sortVisible = ref(false)
const draft = ref<MenuNode[]>([])
const saving = ref(false)
const dragIndex = ref(-1)

function openSort() {
  draft.value = [...zones.value]
  sortVisible.value = true
}

function onDragStart(i: number) {
  dragIndex.value = i
}

function onDrop(i: number) {
  const from = dragIndex.value
  dragIndex.value = -1
  if (from < 0 || from === i) return
  const [item] = draft.value.splice(from, 1)
  if (!item) return
  draft.value.splice(i, 0, item)
}

async function saveSort() {
  saving.value = true
  try {
    await persistOrder(draft.value.map((n) => n.id).join(','))
    sortVisible.value = false
    ElMessage.success(t('common.message.saveSuccess'))
  } finally {
    saving.value = false
  }
}

async function resetSort() {
  saving.value = true
  try {
    await persistOrder('')
    sortVisible.value = false
    ElMessage.success(t('common.message.saveSuccess'))
  } finally {
    saving.value = false
  }
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
      <SideNavItem v-for="node in topMenus" :key="node.id" :node="node" />
      <div v-for="zone in zones" :key="zone.id" class="nav-zone">
        <div class="nav-zone-title">{{ menuTitle(zone) }}</div>
        <SideNavItem v-for="child in zone.children" :key="child.id" :node="child" />
      </div>
    </ElMenu>
    <div class="nav-footer">
      <button type="button" class="nav-sort-btn" :title="t('common.navSort.customize')" @click="openSort">
        <ElIcon><Operation /></ElIcon>
        <span class="nav-label">{{ t('common.navSort.customize') }}</span>
      </button>
    </div>

    <ElDialog v-model="sortVisible" :title="t('common.navSort.title')" width="360px" append-to-body>
      <p class="sort-hint">{{ t('common.navSort.hint') }}</p>
      <ul class="sort-list">
        <li
          v-for="(node, i) in draft"
          :key="node.id"
          class="sort-item"
          :class="{ dragging: dragIndex === i }"
          draggable="true"
          @dragstart="onDragStart(i)"
          @dragover.prevent
          @drop="onDrop(i)"
          @dragend="dragIndex = -1"
        >
          <ElIcon class="drag-handle"><Rank /></ElIcon>
          <span>{{ menuTitle(node) }}</span>
        </li>
      </ul>
      <template #footer>
        <ElButton :disabled="saving" @click="resetSort">{{ t('common.navSort.resetDefault') }}</ElButton>
        <ElButton :disabled="saving" @click="sortVisible = false">{{ t('common.action.cancel') }}</ElButton>
        <ElButton type="primary" :loading="saving" @click="saveSort">{{ t('common.action.save') }}</ElButton>
      </template>
    </ElDialog>
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

.side-nav.collapsed .nav-zone-title {
  display: none;
}

.nav-label {
  margin-left: 6px;
}

.side-nav.collapsed .nav-label {
  display: none;
}

.nav-footer {
  flex: none;
  border-top: 1px solid var(--bs-color-border-default);
  padding: var(--bs-space-1);
}

.nav-sort-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  height: var(--bs-density-nav-item-height);
  border: none;
  border-radius: var(--bs-radius-md);
  background: transparent;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
  cursor: pointer;
}

.nav-sort-btn:hover {
  background: var(--bs-color-fill-light);
  color: var(--bs-color-primary);
}

.sort-hint {
  margin: 0 0 var(--bs-space-2);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.sort-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.sort-item {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  padding: var(--bs-space-2);
  border: 1px solid var(--bs-color-border-default);
  border-radius: var(--bs-radius-md);
  margin-bottom: var(--bs-space-1);
  background: var(--bs-color-bg-surface);
  cursor: grab;
  user-select: none;
}

.sort-item.dragging {
  opacity: 0.5;
  border-style: dashed;
}

.drag-handle {
  color: var(--bs-color-fg-muted);
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
