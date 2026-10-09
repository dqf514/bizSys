import { onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useTabsStore } from '@/stores/tabs'

const commandVisible = ref(false)

export function useCommandPalette() {
  return { commandVisible }
}

export function useHotkeys() {
  const router = useRouter()

  function onKeydown(e: KeyboardEvent) {
    const target = e.target as HTMLElement | null
    const typing =
      target &&
      (target.tagName === 'INPUT' ||
        target.tagName === 'TEXTAREA' ||
        target.isContentEditable)

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
      e.preventDefault()
      commandVisible.value = !commandVisible.value
      return
    }

    // Ctrl+N: quick create — open the command palette
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n') {
      if (typing) return
      e.preventDefault()
      commandVisible.value = true
      return
    }

    // Esc: close the top-most overlay we own (command palette); ElDialog handles its own
    if (e.key === 'Escape' && commandVisible.value) {
      commandVisible.value = false
      return
    }

    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'w') {
      if (typing) return
      e.preventDefault()
      const tabs = useTabsStore()
      const active = tabs.tabs.find((t) => t.key === tabs.active)
      if (active && !active.pinned) {
        tabs.close(active.key, true)
        const next = tabs.tabs.find((x) => x.key === tabs.active) ?? tabs.tabs[0]
        if (next) router.push(next.fullPath || next.path)
        else router.push('/workbench')
      }
      return
    }

    if (e.altKey && e.key >= '1' && e.key <= '9') {
      e.preventDefault()
      const tabs = useTabsStore()
      const idx = Number(e.key) - 1
      const tab = tabs.tabs[idx]
      if (tab) {
        tabs.setActive(tab.key)
        router.push(tab.fullPath || tab.path)
      }
    }
  }

  onMounted(() => window.addEventListener('keydown', onKeydown))
  onUnmounted(() => window.removeEventListener('keydown', onKeydown))

  return { commandVisible }
}
