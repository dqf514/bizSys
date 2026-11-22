/** 列表表格的列定义（桌面表格 / 移动卡片共用） */
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
  /** 后端排序字段名（snake_case，须在接口 sort 白名单内）；'local' 为前端本地排序（按 prop 取值）；不传则不可排序 */
  sortable?: string
  align?: 'left' | 'center' | 'right'
}

export interface SortChange {
  prop: string
  order: 'ascending' | 'descending' | null
  sortField?: string
}
