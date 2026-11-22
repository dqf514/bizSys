<script setup lang="ts">
/**
 * 响应式列表：桌面用 el-table，窄屏（<768px）自动降级为卡片流。
 *
 * - 卡片模式：第一列作为卡片标题，其余列渲染为「标签：值」行；
 * - 单元格内容统一走 `cell` 具名作用域插槽（参数 { row, col }），
 *   未提供时回落到 prop 原值 —— 这样桌面表格与移动卡片永远同源。
 */
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useIsMobile } from '@/composables/useIsMobile'
import type { ListColumn, SortChange } from '@/components/list/types'

const props = defineProps<{
  columns: ListColumn[]
  data: Record<string, unknown>[]
  loading?: boolean
  total?: number
  page?: number
  size?: number
  selectable?: boolean
  rowKey?: string
  height?: string | number
  /** 内嵌表格（详情页页签）可关闭分页条 */
  showPagination?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:page', v: number): void
  (e: 'update:size', v: number): void
  (e: 'selection-change', rows: Record<string, unknown>[]): void
  (e: 'row-click', row: Record<string, unknown>): void
  (e: 'sort-change', payload: SortChange): void
}>()

defineSlots<{
  /** 单元格内容；row 保持 any 以兼容各页面既有插槽的类型期望 */
  cell(props: { row: any; col: ListColumn }): any
  extraColumns(props: Record<string, never>): any
  cardExtra(props: { row: any }): any
  cardFooter(props: { row: any }): any
}>()

const { t } = useI18n()
const { isMobile } = useIsMobile()

const titleCol = computed<ListColumn | undefined>(() => props.columns[0])
const detailCols = computed<ListColumn[]>(() => props.columns.slice(1))
const paginationLayout = computed(() =>
  isMobile.value ? 'prev, pager, next' : 'sizes, prev, pager, next, jumper',
)

function labelOf(col: ListColumn) {
  return col.labelKey ? t(col.labelKey) : (col.label ?? col.prop)
}

function rowKeyOf(row: Record<string, unknown>) {
  return String(row[props.rowKey || 'id'] ?? '')
}

function onSortChange(payload: { prop: string; order: 'ascending' | 'descending' | null }) {
  const col = props.columns.find((c) => c.prop === payload.prop)
  const sortField = col?.sortable && col.sortable !== 'local' ? col.sortable : undefined
  emit('sort-change', { ...payload, sortField })
}
</script>

<template>
  <div class="responsive-table">
    <!-- 桌面：标准表格 -->
    <el-table
      v-if="!isMobile"
      :data="props.data"
      :loading="props.loading"
      :row-key="props.rowKey || 'id'"
      :height="props.height || '100%'"
      stripe
      border
      size="small"
      class="table"
      @selection-change="(rows: Record<string, unknown>[]) => emit('selection-change', rows)"
      @row-click="(row: Record<string, unknown>) => emit('row-click', row)"
      @sort-change="onSortChange"
    >
      <el-table-column v-if="props.selectable" type="selection" width="40" fixed="left" />
      <el-table-column
        v-for="col in props.columns"
        :key="col.prop"
        :prop="col.prop"
        :label="labelOf(col)"
        :width="col.width"
        :min-width="col.minWidth || 100"
        :fixed="col.fixed"
        :align="col.align"
        :sortable="col.sortable === 'local' ? true : col.sortable ? 'custom' : false"
        :show-overflow-tooltip="col.showOverflowTooltip ?? true"
      >
        <template #default="{ row }">
          <slot name="cell" :row="row" :col="col">{{ row[col.prop] ?? '-' }}</slot>
        </template>
      </el-table-column>
      <slot name="extraColumns" />
    </el-table>

    <!-- 移动：卡片流 -->
    <div v-else v-loading="props.loading" class="card-list">
      <el-empty v-if="!props.data.length" :description="t('common.table.empty')" />
      <article
        v-for="row in props.data"
        :key="rowKeyOf(row)"
        class="card-item"
        @click="emit('row-click', row)"
      >
        <div v-if="titleCol" class="card-item-head">
          <span class="card-item-title">
            <slot name="cell" :row="row" :col="titleCol">{{ row[titleCol.prop] ?? '-' }}</slot>
          </span>
          <slot name="cardExtra" :row="row" />
        </div>
        <div class="card-item-body">
          <div v-for="col in detailCols" :key="col.prop" class="card-item-row">
            <span class="card-item-label">{{ labelOf(col) }}</span>
            <span class="card-item-value">
              <slot name="cell" :row="row" :col="col">{{ row[col.prop] ?? '-' }}</slot>
            </span>
          </div>
        </div>
        <slot name="cardFooter" :row="row" />
      </article>
    </div>

    <div v-if="props.showPagination !== false" class="table-pagination">
      <span class="total-text">{{ t('common.table.total', { total: props.total ?? 0 }) }}</span>
      <el-pagination
        :current-page="props.page || 1"
        :page-size="props.size || 20"
        :total="props.total || 0"
        :page-sizes="[10, 20, 50, 100]"
        :layout="paginationLayout"
        background
        @current-change="emit('update:page', $event)"
        @size-change="emit('update:size', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.responsive-table {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--bs-color-bg-surface);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  overflow: hidden;
}

.table {
  flex: 1;
  min-height: 0;
}

.card-list {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  padding: var(--bs-space-2);
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.card-item {
  padding: var(--bs-space-3);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.card-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bs-space-2);
}

.card-item-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
  min-width: 0;
  word-break: break-all;
}

.card-item-body {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-1);
}

.card-item-row {
  display: flex;
  gap: var(--bs-space-3);
  align-items: baseline;
}

.card-item-label {
  flex: none;
  width: 84px;
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.card-item-value {
  flex: 1;
  min-width: 0;
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-default);
  word-break: break-all;
}

.table-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bs-space-3);
  padding: var(--bs-space-2) var(--bs-space-3);
  border-top: 1px solid var(--bs-color-border-subtle);
  background: var(--bs-color-bg-surface);
  flex-shrink: 0;
}

.total-text {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

:deep(.el-table) {
  --el-table-row-hover-bg-color: var(--bs-color-fill-hover);
  --el-table-header-bg-color: var(--bs-color-fill-lighter);
  --el-table-border-color: var(--bs-color-border-subtle);
  font-size: var(--bs-density-font-size);
}

:deep(.el-table th.el-table__cell) {
  height: var(--bs-density-table-header-height);
  padding: 0;
}

:deep(.el-table td.el-table__cell) {
  height: var(--bs-density-table-row-height);
  padding: 0;
}
</style>
