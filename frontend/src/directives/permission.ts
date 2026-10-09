import type { Directive, DirectiveBinding } from 'vue'
import { useAuthStore } from '@/stores/auth'

function check(el: HTMLElement, binding: DirectiveBinding<string>) {
  const code = binding.value
  if (!code) return
  const auth = useAuthStore()
  if (!auth.hasPerm(code)) {
    el.parentNode?.removeChild(el)
  }
}

export const permission: Directive<HTMLElement, string> = {
  mounted: check,
  updated: check,
}

export default permission
