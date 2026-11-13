/**
 * 图表语义色板（canvas / SVG attribute 场景统一入口）。
 *
 * ECharts 的颜色落在 canvas 像素、LogicFlow 落在 SVG presentation attribute，均不支持 var()，
 * 因此统一用 getComputedStyle 把 --bs-* 令牌解析为字面值；fallback 仅在令牌缺失时兜底。
 * 主题/明暗/accent 切换后必须重绘：调用方挂 watchChartTheme(redraw)。
 */
import { watch } from 'vue'
import { useThemeStore } from '@/stores/theme'

export function resolveToken(name: string, fallback: string): string {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

/** 8 色分类色板（--bs-color-chart-1..8）：多序列图表/快捷方式 chip 统一取色 */
export function chartPalette(): string[] {
  const fallbacks = ['#2563eb', '#0891b2', '#16a34a', '#d97706', '#ea580c', '#dc2626', '#7c3aed', '#db2777']
  return fallbacks.map((fb, i) => resolveToken(`--bs-color-chart-${i + 1}`, fb))
}

/** 任务/流程状态 → 语义令牌（状态色随明暗主题自适应） */
const STATUS_TOKEN: Record<string, [token: string, fallback: string]> = {
  draft: ['--bs-color-fg-muted', '#909399'],
  approving: ['--bs-color-semantic-warning', '#d97706'],
  rejected: ['--bs-color-semantic-danger', '#dc2626'],
  in_progress: ['--bs-color-primary', '#2563eb'],
  finished: ['--bs-color-semantic-success', '#16a34a'],
  settled: ['--bs-color-chart-2', '#0891b2'],
  stopped: ['--bs-color-semantic-danger', '#dc2626'],
}

export function statusColor(status: string): string {
  const [name, fb] = STATUS_TOKEN[status] ?? ['--bs-color-fg-muted', '#909399']
  return resolveToken(name, fb)
}

/**
 * 主题/明暗/accent 变化后重绘图表。
 * flush: 'post' 保证 theme store 已把 data-theme/data-accent 写到 <html> 再读计算样式。
 */
export function watchChartTheme(redraw: () => void) {
  const theme = useThemeStore()
  watch(
    () => [theme.theme, theme.accent],
    () => redraw(),
    { flush: 'post' },
  )
}
