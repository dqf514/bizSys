<script setup lang="ts">
import { computed, h, ref, resolveComponent, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { ElIcon, ElMessage } from 'element-plus'
import { Bottom, Delete, Plus, Top } from '@element-plus/icons-vue'
import { DEFAULT_DOCK_PATHS, DOCK_MAX, dockSettingsVisible, useDock } from './useDock'
import type { MenuNode } from '@/api/types'

const { t } = useI18n()
const { items, available, persist } = useDock()

const selected = ref<string[]>([])
const saving = ref(false)

// 每次打开同步当前生效列表（已解析：含默认值回退与权限过滤）
watch(dockSettingsVisible, (v) => {
  if (v) selected.value = items.value.map((i) => i.path)
})

function titleOf(node: MenuNode) {
  return node.titleKey ? t(node.titleKey) : node.name
}

function renderIcon(icon?: string) {
  if (!icon) return null
  const comp = resolveComponent(icon)
  return comp ? h(comp as never) : null
}

const availableNodes = computed(() => {
  const picked = new Set(selected.value)
  return available.value.filter((n) => !picked.has(n.path))
})

const selectedNodes = computed(() => {
  const byPath = new Map(available.value.map((n) => [n.path, n]))
  return selected.value.map((p) => byPath.get(p)).filter((n): n is MenuNode => Boolean(n))
})

function add(path: string) {
  if (selected.value.length >= DOCK_MAX) {
    ElMessage.warning(t('common.dock.limitTip'))
    return
  }
  selected.value.push(path)
}

function remove(path: string) {
  selected.value = selected.value.filter((p) => p !== path)
}

function move(index: number, delta: -1 | 1) {
  const target = index + delta
  if (target < 0 || target >= selected.value.length) return
  const list = [...selected.value]
  const [item] = list.splice(index, 1)
  if (item === undefined) return
  list.splice(target, 0, item)
  selected.value = list
}

function resetDefault() {
  const ok = new Set(available.value.map((n) => n.path))
  selected.value = DEFAULT_DOCK_PATHS.filter((p) => ok.has(p))
}

async function save() {
  saving.value = true
  try {
    await persist(selected.value)
    dockSettingsVisible.value = false
    ElMessage.success(t('common.message.saveSuccess'))
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <el-dialog
    v-model="dockSettingsVisible"
    :title="t('common.dock.settings')"
    width="520px"
    append-to-body
    class="dock-settings-dialog"
  >
    <p class="dock-hint">{{ t('common.dock.hint') }}</p>

    <div class="dock-section-title">{{ t('common.dock.selected') }}（{{ selected.length }}/{{ DOCK_MAX }}）</div>
    <div v-if="selectedNodes.length" class="dock-list">
      <div v-for="(node, i) in selectedNodes" :key="node.path" class="dock-row">
        <ElIcon v-if="node.icon"><component :is="renderIcon(node.icon)" /></ElIcon>
        <span class="dock-row-title">{{ titleOf(node) }}</span>
        <button
          type="button"
          class="row-btn"
          :disabled="i === 0"
          :aria-label="t('common.action.moveUp')"
          @click="move(i, -1)"
        >
          <ElIcon><Top /></ElIcon>
        </button>
        <button
          type="button"
          class="row-btn"
          :disabled="i === selectedNodes.length - 1"
          :aria-label="t('common.action.moveDown')"
          @click="move(i, 1)"
        >
          <ElIcon><Bottom /></ElIcon>
        </button>
        <button
          type="button"
          class="row-btn danger"
          :aria-label="t('common.action.delete')"
          @click="remove(node.path)"
        >
          <ElIcon><Delete /></ElIcon>
        </button>
      </div>
    </div>
    <p v-else class="dock-empty">{{ t('common.dock.emptySelected') }}</p>

    <div class="dock-section-title">{{ t('common.dock.available') }}</div>
    <div v-if="availableNodes.length" class="dock-list dock-list-scroll">
      <div v-for="node in availableNodes" :key="node.path" class="dock-row">
        <ElIcon v-if="node.icon"><component :is="renderIcon(node.icon)" /></ElIcon>
        <span class="dock-row-title">{{ titleOf(node) }}</span>
        <button
          type="button"
          class="row-btn add"
          :aria-label="t('common.action.add')"
          @click="add(node.path)"
        >
          <ElIcon><Plus /></ElIcon>
        </button>
      </div>
    </div>
    <p v-else class="dock-empty">{{ t('common.dock.emptyAvailable') }}</p>

    <template #footer>
      <el-button class="bs-float-left" @click="resetDefault">{{ t('common.dock.resetDefault') }}</el-button>
      <el-button @click="dockSettingsVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.dock-hint {
  margin: 0 0 var(--bs-space-3);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.dock-section-title {
  margin: var(--bs-space-2) 0 var(--bs-space-1);
  font-size: var(--bs-typography-font-size-xs);
  font-weight: 600;
  color: var(--bs-color-fg-secondary);
}

.dock-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.dock-list-scroll {
  max-height: 40vh;
  overflow-y: auto;
}

.dock-row {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  padding: var(--bs-space-1) var(--bs-space-2);
  border-radius: var(--bs-radius-sm);
  color: var(--bs-color-fg-default);
  font-size: var(--bs-typography-font-size-sm);
}

.dock-row:hover {
  background: var(--bs-color-fill-hover);
}

.dock-row-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.row-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: var(--bs-radius-sm);
  background: transparent;
  color: var(--bs-color-fg-secondary);
  cursor: pointer;
}

.row-btn:hover:not(:disabled) {
  background: var(--bs-color-fill-light);
  color: var(--bs-color-primary);
}

.row-btn:disabled {
  opacity: 0.35;
  cursor: not-allowed;
}

.row-btn.danger:hover:not(:disabled) {
  color: var(--bs-color-semantic-danger);
}

.dock-empty {
  margin: 0 0 var(--bs-space-2);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.bs-float-left {
  float: left;
}
</style>
