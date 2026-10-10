<script setup lang="ts">
import { computed, ref } from 'vue'
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

/** per-user top-level order stored as CSV of menu ids in prefs.navOrder */
const customOrder = computed<number[]>(() => {
  const raw = auth.user?.prefs?.navOrder
  if (typeof raw !== 'string' || !raw) return []
  return raw
    .split(',')
    .map((s) => Number(s))
    .filter((n) => Number.isFinite(n))
})

const menus = computed(() => {
  const tree = visibleMenus(auth.menus)
  const order = customOrder.value
  if (!order.length) return tree
  const rank = new Map(order.map((id, i) => [id, i]))
  // items missing from the saved order keep their default relative order at the end (stable sort)
  return [...tree].sort((a, b) => (rank.get(a.id) ?? Infinity) - (rank.get(b.id) ?? Infinity))
})

// ---- customize dialog ----
const sortVisible = ref(false)
const draft = ref<MenuNode[]>([])
const saving = ref(false)
const dragIndex = ref(-1)

function openSort() {
  draft.value = [...menus.value]
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

async function persistOrder(csv: string) {
  await authApi.updatePrefs({ navOrder: csv })
  if (auth.user) auth.user.prefs = { ...(auth.user.prefs ?? {}), navOrder: csv }
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
      <SideNavItem v-for="node in menus" :key="node.id" :node="node" />
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
          <span>{{ node.titleKey ? t(node.titleKey) : node.name }}</span>
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
