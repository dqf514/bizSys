import { ref } from 'vue'

export const MOBILE_QUERY = '(max-width: 767px)'

const mql = typeof window !== 'undefined' ? window.matchMedia(MOBILE_QUERY) : null

/** 全局共享的移动端断点（<768px）响应式标志 */
export const isMobile = ref(mql?.matches ?? false)

mql?.addEventListener('change', (e) => {
  isMobile.value = e.matches
})

export function useIsMobile() {
  return { isMobile }
}
