<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

export interface ListColumn {
  prop: string
  labelKey?: string
  label?: string
  width?: number
  minWidth?: number
  fixed?: boolean | 'left' | 'right'
  slot?: string
  formatter?: (row: Record<string, unknown>) => string
  showOverflowTooltip?: boolean
}

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
}>()

const emit = defineEmits<{
  (e: 'update:page', v: number): void
  (e: 'update:size', v: number): void
  (e: 'selection-change', rows: Record<string, unknown>[]): void
  (e: 'row-click', row: Record<string, unknown>): void
}>()

const { t } = useI18n()
const selected = ref<Record<string, unknown>[]>([])

watch(
  () => props.data,
  () => {
    selected.value = []
  },
)

function labelOf(col: ListColumn) {
  return col.labelKey ? t(col.labelKey) : (col.label ?? col.prop)
}

function onSelectionChange(rows: Record<string, unknown>[]) {
  selected.value = rows
  emit('selection-change', rows)
}
</script>

<template>
  <div class="list-table">
    <el-table
      :data="props.data"
      :loading="props.loading"
      :row-key="props.rowKey || 'id'"
      :height="props.height || '100%'"
      stripe
      border
      size="small"
      class="table"
      @selection-change="onSelectionChange"
      @row-click="(row: Record<string, unknown>) => emit('row-click', row)"
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
        :show-overflow-tooltip="col.showOverflowTooltip ?? true"
      >
        <template #default="{ row }">
          <slot :name="col.slot || col.prop" :row="row">
            <span>{{ col.formatter ? col.formatter(row) : (row[col.prop] ?? '-') }}</span>
          </slot>
        </template>
      </el-table-column>
      <slot name="extraColumns" />
    </el-table>

    <div class="list-table-pagination">
      <span class="total-text">{{ t('common.table.total', { total: props.total ?? 0 }) }}</span>
      <el-pagination
        :current-page="props.page || 1"
        :page-size="props.size || 20"
        :total="props.total || 0"
        :page-sizes="[10, 20, 50, 100]"
        layout="sizes, prev, pager, next, jumper"
        background
        @current-change="emit('update:page', $event)"
        @size-change="emit('update:size', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.list-table {
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

.list-table-pagination {
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
