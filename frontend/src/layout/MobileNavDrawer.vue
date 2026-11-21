<script setup lang="ts">
import { computed, h, resolveComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElDrawer, ElIcon } from 'element-plus'
import { ArrowRight } from '@element-plus/icons-vue'
import { countZoneItems, useNavZones } from './useNavZones'
import { useBrandingStore } from '@/stores/branding'
import type { MenuNode } from '@/api/types'

const visible = defineModel<boolean>({ required: true })

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const branding = useBrandingStore()

const { topMenus, zones, systemZone, menuTitle, toggleZone, isZoneOpen } = useNavZones()

const brandText = computed(() => branding.siteName || t('common.app.short'))

function renderIcon(icon?: string) {
  if (!icon) return null
  const comp = resolveComponent(icon)
  return comp ? h(comp as never) : null
}

function go(node: MenuNode) {
  if (!node.path) return
  visible.value = false
  router.push(node.path)
}

function isActive(node: MenuNode) {
  if (!node.path) return false
  return route.path === node.path || route.path.startsWith(`${node.path}/`)
}

/** 分区头按钮的无障碍描述：分区名 + 展开/收起动作 */
function zoneToggleLabel(zone: MenuNode) {
  const action = isZoneOpen(zone) ? t('common.nav.collapseZone') : t('common.nav.expandZone')
  return `${menuTitle(zone)} - ${action}`
}
</script>

<template>
  <ElDrawer
    v-model="visible"
    direction="ltr"
    size="82%"
    class="mobile-nav-drawer"
    :with-header="false"
  >
    <div class="drawer-brand">
      <img v-if="branding.logoUrl" :src="branding.logoUrl" :alt="brandText" class="brand-logo" />
      <span class="brand-text">{{ brandText }}</span>
    </div>

    <div class="drawer-body">
      <button
        v-for="node in topMenus"
        :key="node.id"
        type="button"
        class="nav-item"
        :class="{ active: isActive(node) }"
        @click="go(node)"
      >
        <ElIcon v-if="node.icon"><component :is="renderIcon(node.icon)" /></ElIcon>
        <span class="nav-text">{{ menuTitle(node) }}</span>
      </button>

      <!-- 分区手风琴：与桌面侧栏共用同一展开状态（bs.navZoneOpen） -->
      <div v-for="zone in zones" :key="zone.id" class="nav-group" :class="{ open: isZoneOpen(zone) }">
        <button
          type="button"
          class="nav-group-title nav-group-toggle"
          :aria-expanded="isZoneOpen(zone)"
          :aria-label="zoneToggleLabel(zone)"
          @click="toggleZone(zone)"
        >
          <ElIcon class="nav-group-caret"><ArrowRight /></ElIcon>
          <span class="nav-group-name">{{ menuTitle(zone) }}</span>
          <span class="nav-group-count">{{ countZoneItems(zone) }}</span>
        </button>
        <div v-show="isZoneOpen(zone)" class="nav-group-body">
          <template v-for="child in zone.children" :key="child.id">
            <template v-if="child.menuType === 'dir'">
              <div v-if="child.children?.length" class="nav-sub-title">{{ menuTitle(child) }}</div>
              <button
                v-for="leaf in child.children"
                :key="leaf.id"
                type="button"
                class="nav-item nested"
                :class="{ active: isActive(leaf) }"
                @click="go(leaf)"
              >
                <ElIcon v-if="leaf.icon"><component :is="renderIcon(leaf.icon)" /></ElIcon>
                <span class="nav-text">{{ menuTitle(leaf) }}</span>
              </button>
            </template>
            <button
              v-else
              type="button"
              class="nav-item"
              :class="{ active: isActive(child) }"
              @click="go(child)"
            >
              <ElIcon v-if="child.icon"><component :is="renderIcon(child.icon)" /></ElIcon>
              <span class="nav-text">{{ menuTitle(child) }}</span>
            </button>
          </template>
        </div>
      </div>

      <div v-if="systemZone" class="nav-group system-group">
        <div class="nav-group-title">{{ menuTitle(systemZone) }}</div>
        <template v-for="group in systemZone.children" :key="group.id">
          <div v-if="group.children?.length" class="nav-sub-title">{{ menuTitle(group) }}</div>
          <button
            v-for="item in group.children"
            :key="item.id"
            type="button"
            class="nav-item nested"
            :class="{ active: isActive(item) }"
            @click="go(item)"
          >
            <ElIcon v-if="item.icon"><component :is="renderIcon(item.icon)" /></ElIcon>
            <span class="nav-text">{{ menuTitle(item) }}</span>
          </button>
        </template>
      </div>
    </div>
  </ElDrawer>
</template>

<style scoped>
.drawer-brand {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  padding: var(--bs-space-3) var(--bs-space-3) var(--bs-space-2);
  border-bottom: 1px solid var(--bs-color-border-subtle);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.brand-logo {
  max-width: 24px;
  max-height: 24px;
  object-fit: contain;
}

.drawer-body {
  padding: var(--bs-space-2);
  overflow-y: auto;
}

.nav-group {
  margin-top: var(--bs-space-2);
  border-top: 1px solid var(--bs-color-border-subtle);
  padding-top: var(--bs-space-2);
}

.nav-group-title {
  padding: var(--bs-space-1) var(--bs-space-2);
  font-size: var(--bs-typography-font-size-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--bs-color-fg-muted);
  user-select: none;
}

.nav-group-toggle {
  display: flex;
  align-items: center;
  gap: var(--bs-space-1);
  width: 100%;
  min-height: 44px;
  padding: var(--bs-space-2);
  border: none;
  border-radius: var(--bs-radius-md);
  background: transparent;
  font-size: var(--bs-typography-font-size-xs);
  font-weight: 600;
  letter-spacing: 0.06em;
  color: var(--bs-color-fg-muted);
  cursor: pointer;
  text-align: left;
}

.nav-group-toggle:hover {
  background: var(--bs-color-fill-hover);
  color: var(--bs-color-fg-default);
}

.nav-group-caret {
  transition: transform var(--bs-motion-fast) var(--bs-motion-curve);
}

.nav-group.open .nav-group-caret {
  transform: rotate(90deg);
}

.nav-group-name {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav-group-count {
  flex: none;
  font-weight: 400;
  letter-spacing: 0;
  opacity: 0.8;
}

.nav-sub-title {
  padding: var(--bs-space-1) var(--bs-space-2) 2px;
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  user-select: none;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  width: 100%;
  min-height: 44px;
  padding: var(--bs-space-2);
  border: none;
  border-radius: var(--bs-radius-md);
  background: transparent;
  color: var(--bs-color-fg-default);
  font-size: var(--bs-typography-font-size-sm);
  cursor: pointer;
  text-align: left;
}

.nav-item.nested {
  padding-left: var(--bs-space-4);
}

.nav-item:hover {
  background: var(--bs-color-fill-hover);
}

.nav-item.active {
  background: var(--bs-color-brand-primary-soft);
  color: var(--bs-color-primary);
  font-weight: 600;
}

.nav-text {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

</style>

<!-- 非 scoped：全局 mobile.css 会把抽屉统一压到近全宽，导航抽屉需要更窄宽度，靠更高优先级覆盖 -->
<style>
@media (max-width: 767px) {
  div.el-drawer.ltr.mobile-nav-drawer {
    width: min(320px, 82vw) !important;
  }
}
</style>
