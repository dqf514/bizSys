import type { Directive, DirectiveBinding } from 'vue'
import { useAuthStore } from '@/stores/auth'

/**
 * 权限指令：值可以是单个权限码，也可以是权限码数组（任一满足即显示）。
 * 例：`v-permission="'finance:payment:submit'` / `v-permission="['a', 'b']"`。
 */
function check(el: HTMLElement, binding: DirectiveBinding<string | string[]>) {
  const value = binding.value
  if (!value) return
  const codes = Array.isArray(value) ? value.filter(Boolean) : [value]
  if (!codes.length) return
  const auth = useAuthStore()
  if (!codes.some((code) => auth.hasPerm(code))) {
    el.parentNode?.removeChild(el)
  }
}

export const permission: Directive<HTMLElement, string | string[]> = {
  mounted: check,
  updated: check,
}

export default permission
