<script setup lang="ts">
import { computed } from 'vue'
import ResponsiveTable from '@/components/common/ResponsiveTable.vue'
import type { ListColumn, SortChange } from './types'

export type { ListColumn, SortChange }

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
  (e: 'sort-change', payload: SortChange): void
}>()

/**
 * 保证至少有一列是弹性列。
 *
 * Element Plus 的 `el-table` 只拉伸「没有固定 width」的列
 * （table-layout: flexColumns = columns.filter(c => !isNumber(c.width))）；
 * 一旦所有列都写了固定 width，表格宽度 = 列宽之和，内容区右侧会留出大片空白，
 * 与其他板块「表格占满内容区」的观感不一致。这里把最后一列改成弹性列兜底。
 */
const tableColumns = computed<ListColumn[]>(() => {
  const cols = props.columns
  if (!cols.length) return cols
  if (cols.some((c) => c.width === undefined)) return cols
  return cols.map((c, i) =>
    i === cols.length - 1 ? { ...c, width: undefined, minWidth: c.minWidth ?? c.width ?? 100 } : c,
  )
})
</script>

<template>
  <!-- 桌面表格 / 移动卡片由 ResponsiveTable 内部按断点切换 -->
  <ResponsiveTable
    :columns="tableColumns"
    :data="props.data"
    :loading="props.loading"
    :total="props.total"
    :page="props.page"
    :size="props.size"
    :selectable="props.selectable"
    :row-key="props.rowKey"
    :height="props.height"
    @update:page="emit('update:page', $event)"
    @update:size="emit('update:size', $event)"
    @selection-change="emit('selection-change', $event)"
    @row-click="emit('row-click', $event)"
    @sort-change="emit('sort-change', $event)"
  >
    <template #cell="{ row, col }">
      <slot :name="col.slot || col.prop" :row="row">
        <span>{{ col.formatter ? col.formatter(row) : (row[col.prop] ?? '-') }}</span>
      </slot>
    </template>
    <template #extraColumns>
      <slot name="extraColumns" />
    </template>
    <template #cardExtra="{ row }">
      <slot name="cardExtra" :row="row" />
    </template>
    <template #cardFooter="{ row }">
      <slot name="cardFooter" :row="row" />
    </template>
  </ResponsiveTable>
</template>
