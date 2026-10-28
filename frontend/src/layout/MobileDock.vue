<script setup lang="ts">
import { computed, h, ref, resolveComponent } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElIcon } from 'element-plus'
import { openDockSettings, useDock } from './useDock'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const { items, centerItem } = useDock()

/** 中央两侧各 2 槽位，缺项留空保持中央按钮居中 */
const leftItems = computed(() => items.value.slice(0, 2))
const rightItems = computed(() => items.value.slice(2, 4))

function renderIcon(icon?: string) {
  if (!icon) return null
  const comp = resolveComponent(icon)
  return comp ? h(comp as never) : null
}

function go(path: string) {
  if (route.path !== path) router.push(path)
}

// ---- 长按 Dock 打开定制弹窗（头像菜单同样有入口） ----
const LONG_PRESS_MS = 500
let pressTimer: ReturnType<typeof setTimeout> | null = null
const pressing = ref(false)

function onPressStart() {
  pressing.value = true
  pressTimer = setTimeout(() => {
    pressTimer = null
    openDockSettings()
  }, LONG_PRESS_MS)
}

function onPressEnd() {
  pressing.value = false
  if (pressTimer) {
    clearTimeout(pressTimer)
    pressTimer = null
  }
}
</script>

<template>
  <nav
    class="mobile-dock"
    :aria-label="t('common.dock.settings')"
    @touchstart.passive="onPressStart"
    @touchend.passive="onPressEnd"
    @touchcancel.passive="onPressEnd"
    @mousedown="onPressStart"
    @mouseup="onPressEnd"
    @mouseleave="onPressEnd"
  >
    <button
      v-for="item in leftItems"
      :key="item.path"
      type="button"
      class="dock-item"
      :class="{ active: route.path === item.path }"
      @click="go(item.path)"
    >
      <ElIcon :size="20"><component :is="renderIcon(item.icon)" v-if="item.icon" /></ElIcon>
      <span class="dock-label">{{ item.title }}</span>
    </button>
    <span v-for="i in 2 - leftItems.length" :key="`l${i}`" class="dock-slot" />

    <button
      type="button"
      class="dock-center"
      :class="{ active: route.path === centerItem.path }"
      :aria-label="centerItem.title"
      @click="go(centerItem.path)"
    >
      <ElIcon :size="24"><component :is="renderIcon(centerItem.icon)" v-if="centerItem.icon" /></ElIcon>
    </button>

    <button
      v-for="item in rightItems"
      :key="item.path"
      type="button"
      class="dock-item"
      :class="{ active: route.path === item.path }"
      @click="go(item.path)"
    >
      <ElIcon :size="20"><component :is="renderIcon(item.icon)" v-if="item.icon" /></ElIcon>
      <span class="dock-label">{{ item.title }}</span>
    </button>
    <span v-for="i in 2 - rightItems.length" :key="`r${i}`" class="dock-slot" />
  </nav>
</template>

<style scoped>
.mobile-dock {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 2100;
  display: grid;
  grid-template-columns: 1fr 1fr 72px 1fr 1fr;
  align-items: end;
  height: calc(56px + env(safe-area-inset-bottom));
  padding: 0 var(--bs-space-2) env(safe-area-inset-bottom);
  border-top: 1px solid var(--bs-color-border-default);
  background: var(--bs-color-bg-surface);
  user-select: none;
}

.dock-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  height: 56px;
  min-width: 0;
  border: none;
  background: transparent;
  color: var(--bs-color-fg-muted);
  cursor: pointer;
}

.dock-item.active {
  color: var(--bs-color-primary);
}

.dock-label {
  max-width: 100%;
  font-size: 10px;
  line-height: 1.2;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.dock-slot {
  height: 56px;
}

.dock-center {
  justify-self: center;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  margin-bottom: 18px;
  border: none;
  border-radius: var(--bs-radius-full);
  background: var(--bs-color-brand-primary);
  color: var(--bs-color-fg-inverse, #fff);
  box-shadow: var(--bs-shadow-elevation3);
  cursor: pointer;
}

.dock-center:active {
  background: var(--bs-color-brand-primary-active);
}

.dock-center.active {
  box-shadow:
    0 0 0 3px var(--bs-color-bg-surface),
    0 0 0 5px var(--bs-color-brand-primary),
    var(--bs-shadow-elevation3);
}
</style>
