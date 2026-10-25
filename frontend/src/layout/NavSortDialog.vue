<script setup lang="ts">
/** 导航区自定义排序弹窗（区级拖拽排序；工作台固定顶部不参与）。由 SideNav 齿轮 / TopBar 头像菜单打开。 */
import { ref, watch } from 'vue'
import { ElButton, ElDialog, ElIcon, ElMessage } from 'element-plus'
import { Rank } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import type { MenuNode } from '@/api/types'
import { navSortVisible, useNavZones } from './useNavZones'

defineOptions({ name: 'NavSortDialog' })

const { t } = useI18n()
const { zones, menuTitle, persistOrder } = useNavZones()

const draft = ref<MenuNode[]>([])
const saving = ref(false)
const dragIndex = ref(-1)

watch(navSortVisible, (v) => {
  if (v) draft.value = [...zones.value]
})

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
    navSortVisible.value = false
    ElMessage.success(t('common.message.saveSuccess'))
  } finally {
    saving.value = false
  }
}

async function resetSort() {
  saving.value = true
  try {
    await persistOrder('')
    navSortVisible.value = false
    ElMessage.success(t('common.message.saveSuccess'))
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <ElDialog v-model="navSortVisible" :title="t('common.navSort.title')" width="360px" append-to-body>
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
      <ElButton :disabled="saving" @click="navSortVisible = false">{{ t('common.action.cancel') }}</ElButton>
      <ElButton type="primary" :loading="saving" @click="saveSort">{{ t('common.action.save') }}</ElButton>
    </template>
  </ElDialog>
</template>

<style scoped>
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
</style>
