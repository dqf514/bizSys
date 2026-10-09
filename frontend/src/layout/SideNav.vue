<script setup lang="ts">
import { computed, h, resolveComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMenu, ElMenuItem, ElSubMenu, ElIcon } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import type { MenuNode } from '@/api/types'

const props = defineProps<{ collapsed: boolean }>()

const route = useRoute()
const router = useRouter()
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

const menus = computed(() => visibleMenus(auth.menus))

function renderIcon(icon?: string) {
  if (!icon) return null
  const comp = resolveComponent(icon)
  if (!comp) return null
  return h(ElIcon, null, { default: () => h(comp as never) })
}

function go(node: MenuNode) {
  if (node.path) router.push(node.path)
}

function menuTitle(node: MenuNode) {
  return node.titleKey ? t(node.titleKey) : node.name
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
      <template v-for="node in menus" :key="node.id">
        <ElSubMenu v-if="node.menuType === 'dir' && node.children?.length" :index="String(node.id)">
          <template #title>
            <component :is="renderIcon(node.icon)" v-if="node.icon" />
            <span class="nav-label">{{ menuTitle(node) }}</span>
          </template>
          <ElMenuItem
            v-for="child in node.children"
            :key="child.id"
            :index="child.path"
            @click="go(child)"
          >
            <component :is="renderIcon(child.icon)" v-if="child.icon" />
            <span class="nav-label">{{ menuTitle(child) }}</span>
          </ElMenuItem>
        </ElSubMenu>
        <ElMenuItem v-else :index="node.path" @click="go(node)">
          <component :is="renderIcon(node.icon)" v-if="node.icon" />
          <span class="nav-label">{{ menuTitle(node) }}</span>
        </ElMenuItem>
      </template>
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
