<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { DArrowLeft, DArrowRight, Right } from '@element-plus/icons-vue'
import { useContextStore, type ContextSection } from '@/stores/context'

const PANEL_WIDTH = 320
const HANDLE_WIDTH = 28

const context = useContextStore()
const router = useRouter()
const { t, te } = useI18n()

/** Labels/titles may be i18n keys or plain text */
function tr(s: string | undefined) {
  if (!s) return ''
  return te(s) ? t(s) : s
}

const width = computed(() => {
  if (!context.hasContent) return 0
  return context.visible ? PANEL_WIDTH : HANDLE_WIDTH
})

function go(to?: string) {
  if (to) router.push(to)
}

function statColumns(section: ContextSection) {
  return Math.min(3, Math.max(2, section.items.length >= 4 ? 2 : section.items.length || 2))
}
</script>

<template>
  <aside class="context-panel" :style="{ width: `${width}px` }" :class="{ open: context.hasContent && context.visible }">
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
        <section v-for="section in context.sections" :key="section.key" class="ctx-section">
          <div class="section-title">{{ tr(section.title) }}</div>

          <div v-if="section.type === 'fields'" class="field-rows">
            <div v-for="(item, i) in section.items" :key="i" class="field-row">
              <span class="field-label">{{ tr(item.label) }}</span>
              <span class="field-value" :class="{ emphasize: item.emphasize }">{{ item.value ?? '-' }}</span>
            </div>
          </div>

          <div v-else-if="section.type === 'links'" class="link-rows">
            <button
              v-for="(item, i) in section.items"
              :key="i"
              class="link-row"
              type="button"
              @click="go(item.to)"
            >
              <span class="link-label">{{ tr(item.label) }}</span>
              <span v-if="item.value !== undefined" class="link-value">{{ item.value }}</span>
              <el-icon class="link-arrow"><Right /></el-icon>
            </button>
          </div>

          <div v-else class="stat-grid" :style="{ gridTemplateColumns: `repeat(${statColumns(section)}, 1fr)` }">
            <div v-for="(item, i) in section.items" :key="i" class="stat-cell" :class="{ emphasize: item.emphasize }">
              <div class="stat-value">{{ item.value ?? '-' }}</div>
              <div class="stat-label">{{ tr(item.label) }}</div>
            </div>
          </div>
        </section>
      </div>
    </div>

    <el-tooltip v-else-if="context.hasContent" :content="t('common.context.expand')" placement="left">
      <button class="reopen-handle" type="button" @click="context.toggle()">
        <el-icon><DArrowLeft /></el-icon>
      </button>
    </el-tooltip>
  </aside>
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
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-4);
}

.ctx-section {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.section-title {
  font-size: var(--bs-typography-font-size-xs);
  font-weight: 600;
  color: var(--bs-color-fg-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.field-rows {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-1);
}

.field-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--bs-space-2);
  font-size: var(--bs-typography-font-size-sm);
}

.field-label {
  flex-shrink: 0;
  color: var(--bs-color-fg-secondary);
}

.field-value {
  color: var(--bs-color-fg-default);
  text-align: right;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.field-value.emphasize {
  font-weight: 600;
  color: var(--bs-color-semantic-warning);
}

.link-rows {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.link-row {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  width: 100%;
  padding: 6px 8px;
  border: none;
  border-radius: var(--bs-radius-sm);
  background: transparent;
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-default);
  cursor: pointer;
  text-align: left;
}

.link-row:hover {
  background: var(--bs-color-fill-hover);
  color: var(--bs-color-primary);
}

.link-label {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.link-value {
  flex-shrink: 0;
  color: var(--bs-color-fg-muted);
}

.link-arrow {
  flex-shrink: 0;
  color: var(--bs-color-fg-muted);
}

.stat-grid {
  display: grid;
  gap: var(--bs-space-2);
}

.stat-cell {
  padding: var(--bs-space-2);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-sm);
  background: var(--bs-color-bg-app);
}

.stat-cell .stat-value {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 700;
  line-height: 1.2;
  color: var(--bs-color-fg-default);
}

.stat-cell.emphasize .stat-value {
  color: var(--bs-color-semantic-warning);
}

.stat-cell .stat-label {
  margin-top: 2px;
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-secondary);
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
</style>
