<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { DArrowLeft, DArrowRight, InfoFilled } from '@element-plus/icons-vue'
import { ElDrawer } from 'element-plus'
import { useContextStore } from '@/stores/context'
import { useIsMobile } from '@/composables/useIsMobile'
import ContextSections from './ContextSections.vue'

const PANEL_WIDTH = 320
const HANDLE_WIDTH = 28

const context = useContextStore()
const { t, te } = useI18n()
const { isMobile } = useIsMobile()

/** Labels/titles may be i18n keys or plain text */
function tr(s: string | undefined) {
  if (!s) return ''
  return te(s) ? t(s) : s
}

const width = computed(() => {
  if (!context.hasContent) return 0
  return context.visible ? PANEL_WIDTH : HANDLE_WIDTH
})

// ---- 移动端：独立悬浮按钮弹出抽屉（不随 publish 自动展开，避免遮挡内容） ----
const mobileOpen = ref(false)

// 切换记录/切换端时收起，避免陈旧内容占屏
watch(
  () => [context.recordKey, isMobile.value],
  () => {
    mobileOpen.value = false
  },
)
</script>

<template>
  <aside
    v-if="!isMobile"
    class="context-panel"
    :style="{ width: `${width}px` }"
    :class="{ open: context.hasContent && context.visible }"
  >
    <div v-if="context.hasContent && context.visible" class="panel-inner">
      <header class="panel-header">
        <div class="panel-heading">
          <div class="panel-title" :title="tr(context.title)">{{ tr(context.title) || t('common.context.title') }}</div>
          <div v-if="context.subtitle" class="panel-subtitle" :title="tr(context.subtitle)">
            {{ tr(context.subtitle) }}
          </div>
        </div>
        <el-tooltip :content="t('common.context.collapse')" placement="left">
          <button class="icon-btn" type="button" @click="context.close()">
            <el-icon><DArrowRight /></el-icon>
          </button>
        </el-tooltip>
      </header>

      <div class="panel-body">
        <ContextSections />
      </div>
    </div>

    <el-tooltip v-else-if="context.hasContent" :content="t('common.context.expand')" placement="left">
      <button class="reopen-handle bs-fade-in" type="button" @click="context.toggle()">
        <el-icon><DArrowLeft /></el-icon>
      </button>
    </el-tooltip>
  </aside>

  <template v-else>
    <button
      v-if="context.hasContent && !mobileOpen"
      class="ctx-fab"
      type="button"
      :aria-label="t('common.context.expand')"
      @click="mobileOpen = true"
    >
      <el-icon :size="20"><InfoFilled /></el-icon>
    </button>

    <ElDrawer
      v-model="mobileOpen"
      direction="rtl"
      size="88%"
      class="mobile-context-drawer"
      :title="tr(context.title) || t('common.context.title')"
    >
      <div v-if="context.subtitle" class="drawer-subtitle">{{ tr(context.subtitle) }}</div>
      <ContextSections />
    </ElDrawer>
  </template>
</template>

<style scoped>
.context-panel {
  flex-shrink: 0;
  height: 100%;
  overflow: hidden;
  border-left: 1px solid transparent;
  background: var(--bs-color-bg-surface);
  transition: width 0.2s ease;
}

.context-panel.open {
  border-left-color: var(--bs-color-border-default);
}

.panel-inner {
  display: flex;
  flex-direction: column;
  width: 320px;
  height: 100%;
}

.panel-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: var(--bs-space-2);
  padding: var(--bs-space-3) var(--bs-space-3) var(--bs-space-2);
  border-bottom: 1px solid var(--bs-color-border-subtle);
}

.panel-heading {
  min-width: 0;
}

.panel-title {
  font-size: var(--bs-typography-font-size-md);
  font-weight: 600;
  color: var(--bs-color-fg-default);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.panel-subtitle {
  margin-top: 2px;
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: var(--bs-radius-sm);
  background: transparent;
  color: var(--bs-color-fg-muted);
  cursor: pointer;
}

.icon-btn:hover {
  background: var(--bs-color-fill-hover);
  color: var(--bs-color-fg-default);
}

.panel-body {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: var(--bs-space-3);
}

.reopen-handle {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 100%;
  border: none;
  border-left: 1px solid var(--bs-color-border-default);
  background: var(--bs-color-bg-surface);
  color: var(--bs-color-fg-muted);
  cursor: pointer;
}

.reopen-handle:hover {
  color: var(--bs-color-primary);
  background: var(--bs-color-fill-hover);
}

/* 移动端悬浮入口：右缘、底部 Dock 上方 */
.ctx-fab {
  position: fixed;
  right: var(--bs-space-2);
  bottom: calc(72px + env(safe-area-inset-bottom));
  z-index: 2050;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border: none;
  border-radius: var(--bs-radius-full);
  background: var(--bs-color-bg-elevated);
  color: var(--bs-color-primary);
  box-shadow: var(--bs-shadow-elevation3);
  cursor: pointer;
}

.drawer-subtitle {
  margin: calc(-1 * var(--bs-space-2)) 0 var(--bs-space-3);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}
</style>

<!-- 非 scoped：覆盖全局 mobile.css 的近全宽抽屉规则，关联面板保持较窄宽度 -->
<style>
@media (max-width: 767px) {
  div.el-drawer.rtl.mobile-context-drawer {
    width: min(340px, 88vw) !important;
  }
}
</style>
