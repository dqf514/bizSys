<script setup lang="ts">
import { h, resolveComponent } from 'vue'
import { ElMenuItem, ElSubMenu, ElIcon } from 'element-plus'
import { useI18n } from 'vue-i18n'
import type { MenuNode } from '@/api/types'

defineOptions({ name: 'SideNavItem' })
const props = defineProps<{ node: MenuNode; collapsed?: boolean }>()

const { t } = useI18n()

function renderIcon(icon?: string) {
  if (!icon) return null
  const comp = resolveComponent(icon)
  if (!comp) return null
  return h(ElIcon, null, { default: () => h(comp as never) })
}

function menuTitle(node: MenuNode) {
  return node.titleKey ? t(node.titleKey) : node.name
}

/** 折叠态用原生 title 悬浮提示菜单名（el-menu-item 的图标-only 模式） */
function tip(node: MenuNode) {
  return props.collapsed ? menuTitle(node) : undefined
}
</script>

<template>
  <ElSubMenu v-if="node.menuType === 'dir' && node.children?.length" :index="String(node.id)">
    <template #title>
      <component :is="renderIcon(node.icon)" v-if="node.icon" />
      <span class="nav-label">{{ menuTitle(node) }}</span>
    </template>
    <SideNavItem v-for="child in node.children" :key="child.id" :node="child" :collapsed="collapsed" />
  </ElSubMenu>
  <ElMenuItem v-else :index="node.path" :title="tip(node)">
    <component :is="renderIcon(node.icon)" v-if="node.icon" />
    <span class="nav-label">{{ menuTitle(node) }}</span>
  </ElMenuItem>
</template>
