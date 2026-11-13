import { nextTick, onBeforeUnmount, watch, type Ref } from 'vue'

const FOCUSABLE =
  'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), ' +
  'textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

interface PopoverA11yOptions {
  /** 方向键在弹层可交互元素间循环移动焦点（role=menu 型弹层开启） */
  arrowNav?: boolean
}

/**
 * 轻量弹层无障碍增强（ElPopover 等 teleport 到 body 的弹层，按 popper-class 定位）：
 * 打开后焦点移入弹层首个可交互元素；Esc 关闭；焦点在弹层内被关闭时归还触发按钮。
 */
export function usePopoverA11y(
  visible: Ref<boolean>,
  popperClass: string,
  trigger: Ref<HTMLElement | undefined>,
  options: PopoverA11yOptions = {},
) {
  let returnFocus: HTMLElement | null = null
  let closedByEsc = false

  function popper(): HTMLElement | null {
    return document.querySelector<HTMLElement>(`.el-popper.${popperClass}`)
  }

  function focusables(pop: HTMLElement): HTMLElement[] {
    return [...pop.querySelectorAll<HTMLElement>(FOCUSABLE)].filter(
      (el) => el.getBoundingClientRect().width > 0,
    )
  }

  function onKeydown(e: KeyboardEvent) {
    const pop = popper()
    if (!pop) return
    if (e.key === 'Escape') {
      e.stopPropagation()
      closedByEsc = true
      visible.value = false
      return
    }
    if (!options.arrowNav) return
    if (e.key !== 'ArrowDown' && e.key !== 'ArrowUp') return
    if (!pop.contains(e.target as Node)) return
    e.preventDefault()
    const list = focusables(pop)
    if (!list.length) return
    const idx = list.indexOf(document.activeElement as HTMLElement)
    const step = e.key === 'ArrowDown' ? 1 : -1
    list[(idx + step + list.length) % list.length]?.focus()
  }

  watch(visible, async (v) => {
    if (v) {
      returnFocus = document.activeElement as HTMLElement | null
      await nextTick()
      await new Promise((r) => requestAnimationFrame(r))
      const pop = popper()
      if (!pop) return
      const first = focusables(pop)[0]
      if (first) first.focus()
      document.addEventListener('keydown', onKeydown, true)
    } else {
      document.removeEventListener('keydown', onKeydown, true)
      const pop = popper()
      const focusInside = pop ? pop.contains(document.activeElement) : false
      if (closedByEsc || focusInside) {
        const target = returnFocus && document.contains(returnFocus) ? returnFocus : trigger.value
        target?.focus()
      }
      closedByEsc = false
      returnFocus = null
    }
  })

  onBeforeUnmount(() => document.removeEventListener('keydown', onKeydown, true))
}
