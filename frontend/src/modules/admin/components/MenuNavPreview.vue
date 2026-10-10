<script setup lang="ts">
import { ref, resolveComponent } from 'vue'
import { Rank } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import type { MenuNode } from '@/api/types'

defineOptions({ name: 'MenuNavPreview' })

const props = defineProps<{ nodes: MenuNode[]; parentKey: string }>()
const emit = defineEmits<{
  (e: 'move', parentKey: string, from: number, to: number): void
}>()

const { t } = useI18n()

// drag state is per sibling group, so drops can only reorder within the same group
const dragIndex = ref(-1)

function onDragStart(i: number, ev: DragEvent) {
  dragIndex.value = i
  ev.dataTransfer?.setData('text/plain', String(i))
  ev.stopPropagation()
}

function onDrop(i: number, ev: DragEvent) {
  ev.stopPropagation()
  const from = dragIndex.value
  dragIndex.value = -1
  if (from < 0 || from === i) return
  emit('move', props.parentKey, from, i)
}

function title(node: MenuNode) {
  return node.titleKey ? t(node.titleKey) : node.name
}

function iconOf(icon?: string) {
  if (!icon) return null
  return resolveComponent(icon) as never
}
</script>

<template>
  <ul class="mp-list">
    <li
      v-for="(node, i) in nodes"
      :key="node.id"
      class="mp-item"
      :class="{ dragging: dragIndex === i }"
    >
      <div
        class="mp-row"
        draggable="true"
        @dragstart="onDragStart(i, $event)"
        @dragover.prevent
        @drop="onDrop(i, $event)"
        @dragend="dragIndex = -1"
      >
        <el-icon class="mp-handle"><Rank /></el-icon>
        <el-icon v-if="node.icon && iconOf(node.icon)" class="mp-icon">
          <component :is="iconOf(node.icon)" />
        </el-icon>
        <span class="mp-title">{{ title(node) }}</span>
        <el-tag v-if="node.menuType === 'dir'" size="small" effect="plain" class="mp-tag">
          {{ t('admin.menu.typeDir') }}
        </el-tag>
      </div>
      <MenuNavPreview
        v-if="node.children?.length"
        :nodes="node.children"
        :parent-key="String(node.id)"
        @move="(k, f, to) => emit('move', k, f, to)"
      />
    </li>
  </ul>
</template>

<style scoped>
.mp-list {
  list-style: none;
  margin: 0;
  padding: 0;
}

.mp-list .mp-list {
  padding-left: var(--bs-space-4);
}

.mp-row {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  padding: 5px var(--bs-space-2);
  border: 1px solid transparent;
  border-radius: var(--bs-radius-md);
  cursor: grab;
  user-select: none;
}

.mp-row:hover {
  background: var(--bs-color-fill-light);
}

.mp-item.dragging > .mp-row {
  opacity: 0.5;
  border-style: dashed;
  border-color: var(--bs-color-border-default);
}

.mp-handle {
  color: var(--bs-color-fg-muted);
  flex: none;
}

.mp-icon {
  color: var(--bs-color-fg-muted);
  flex: none;
}

.mp-title {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-default);
}

.mp-tag {
  flex: none;
}
</style>
