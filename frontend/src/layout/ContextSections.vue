<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Right } from '@element-plus/icons-vue'
import { useContextStore, type ContextSection } from '@/stores/context'

defineOptions({ name: 'ContextSections' })

const context = useContextStore()
const router = useRouter()
const { te, t } = useI18n()

/** Labels/titles may be i18n keys or plain text */
function tr(s: string | undefined) {
  if (!s) return ''
  return te(s) ? t(s) : s
}

function go(to?: string) {
  if (to) router.push(to)
}

function statColumns(section: ContextSection) {
  return Math.min(3, Math.max(2, section.items.length >= 4 ? 2 : section.items.length || 2))
}
</script>

<template>
  <div class="ctx-sections">
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
</template>

<style scoped>
.ctx-sections {
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
</style>
