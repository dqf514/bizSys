<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElIcon, ElMenu, ElPopover } from 'element-plus'
import { Brush, Operation, Setting, Tools } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore, type Density, type ThemeMode } from '@/stores/theme'
import type { Locale } from '@/i18n'
import SideNavItem from './SideNavItem.vue'
import NavSortDialog from './NavSortDialog.vue'
import { openNavSort, useNavZones } from './useNavZones'

const props = defineProps<{ collapsed: boolean }>()

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const theme = useThemeStore()
const { t } = useI18n()

const active = computed(() => route.path)

const { topMenus, zones, customOrder, validOrder, zoneDirs, menuTitle, persistOrder } = useNavZones()

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

// ---- 底部齿轮：设置弹层（系统设置[需权限] / 自定义排序 / 外观 / 语言） ----
const settingsVisible = ref(false)

const themeModes: { value: ThemeMode; labelKey: string }[] = [
  { value: 'light', labelKey: 'common.theme.light' },
  { value: 'dark', labelKey: 'common.theme.dark' },
  { value: 'brand-smvic', labelKey: 'common.theme.brand' },
]

const densities: { value: Density; labelKey: string }[] = [
  { value: 'comfortable', labelKey: 'common.theme.comfortable' },
  { value: 'compact', labelKey: 'common.theme.compact' },
]

const locales: { value: Locale; labelKey: string }[] = [
  { value: 'zh-CN', labelKey: 'common.lang.zhCN' },
  { value: 'en-US', labelKey: 'common.lang.enUS' },
]

function openSettings() {
  settingsVisible.value = false
  router.push('/admin/settings')
}

function openSort() {
  settingsVisible.value = false
  openNavSort()
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
      <ElPopover
        v-model:visible="settingsVisible"
        trigger="click"
        placement="top-start"
        :width="280"
        popper-class="nav-settings-pop"
      >
        <template #reference>
          <button type="button" class="nav-gear-btn" :title="t('common.nav.settings')">
            <ElIcon><Setting /></ElIcon>
            <span class="nav-label">{{ t('common.nav.settings') }}</span>
          </button>
        </template>

        <div class="settings-panel">
          <button
            v-if="auth.hasPerm('admin:setting:list')"
            class="panel-item"
            type="button"
            @click="openSettings"
          >
            <ElIcon><Tools /></ElIcon>{{ t('common.nav.settings') }}
          </button>
          <button class="panel-item" type="button" @click="openSort">
            <ElIcon><Operation /></ElIcon>{{ t('common.nav.customize') }}
          </button>

          <div class="panel-divider" />

          <div class="panel-section">
            <div class="panel-label">
              <ElIcon><Brush /></ElIcon>{{ t('common.theme.appearance') }}
            </div>
            <div class="seg-row">
              <button
                v-for="m in themeModes"
                :key="m.value"
                type="button"
                class="seg-btn"
                :class="{ active: theme.theme === m.value }"
                @click="theme.setTheme(m.value)"
              >
                {{ t(m.labelKey) }}
              </button>
            </div>
            <div class="seg-row">
              <button
                v-for="d in densities"
                :key="d.value"
                type="button"
                class="seg-btn"
                :class="{ active: theme.density === d.value }"
                @click="theme.setDensity(d.value)"
              >
                {{ t(d.labelKey) }}
              </button>
            </div>
          </div>

          <div class="panel-section">
            <div class="panel-label">{{ t('common.lang.switch') }}</div>
            <div class="seg-row">
              <button
                v-for="l in locales"
                :key="l.value"
                type="button"
                class="seg-btn"
                :class="{ active: theme.locale === l.value }"
                @click="theme.setAppLocale(l.value)"
              >
                {{ t(l.labelKey) }}
              </button>
            </div>
          </div>
        </div>
      </ElPopover>
    </div>

    <NavSortDialog />
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

.nav-gear-btn {
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

.nav-gear-btn:hover {
  background: var(--bs-color-fill-light);
  color: var(--bs-color-primary);
}

.settings-panel {
  display: flex;
  flex-direction: column;
}

.panel-item {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  width: 100%;
  padding: var(--bs-space-2);
  border: none;
  border-radius: var(--bs-radius-sm);
  background: transparent;
  color: var(--bs-color-fg-default);
  font-size: var(--bs-typography-font-size-sm);
  cursor: pointer;
  text-align: left;
}

.panel-item:hover {
  background: var(--bs-color-fill-hover);
}

.panel-divider {
  height: 1px;
  margin: var(--bs-space-1) 0;
  background: var(--bs-color-border-subtle);
}

.panel-section {
  padding: var(--bs-space-1) var(--bs-space-2) var(--bs-space-2);
}

.panel-label {
  display: flex;
  align-items: center;
  gap: var(--bs-space-1);
  margin-bottom: var(--bs-space-1);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.seg-row {
  display: flex;
  gap: var(--bs-space-1);
  margin-bottom: var(--bs-space-1);
}

.seg-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px var(--bs-space-2);
  border: 1px solid var(--bs-color-border-default);
  border-radius: var(--bs-radius-sm);
  background: var(--bs-color-bg-surface);
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-xs);
  cursor: pointer;
}

.seg-btn.active {
  border-color: var(--bs-color-primary);
  color: var(--bs-color-primary);
  background: var(--bs-color-brand-primary-soft);
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
