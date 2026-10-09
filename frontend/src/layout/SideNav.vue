<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { ElMenu } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import type { MenuNode } from '@/api/types'
import SideNavItem from './SideNavItem.vue'

const props = defineProps<{ collapsed: boolean }>()

const route = useRoute()
const auth = useAuthStore()

const active = computed(() => route.path)

function visibleMenus(nodes: MenuNode[]): MenuNode[] {
  return nodes
    .filter((n) => n.visible !== 0 && (n.menuType === 'dir' || n.menuType === 'menu'))
    .map((n) => ({ ...n, children: visibleMenus(n.children ?? []) }))
    .filter((n) => n.menuType === 'menu' || (n.children?.length ?? 0) > 0)
    .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0))
}

const menus = computed(() => visibleMenus(auth.menus))
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
  </div>
</template>

<style scoped>
.side-nav {
  height: 100%;
  overflow: hidden auto;
}

.nav-menu {
  border-right: none;
  height: 100%;
  background: transparent;
}

.nav-label {
  margin-left: 6px;
}

.side-nav.collapsed .nav-label {
  display: none;
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
