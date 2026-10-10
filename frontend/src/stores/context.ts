import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

export interface ContextItem {
  /** i18n key or plain text */
  label: string
  value?: string | number
  /** route path for 'links' sections */
  to?: string
  emphasize?: boolean
}

export interface ContextSection {
  key: string
  /** i18n key or plain text */
  title: string
  type: 'fields' | 'links' | 'stats'
  items: ContextItem[]
}

export interface ContextPayload {
  /** i18n key or plain text */
  title: string
  subtitle?: string
  sections: ContextSection[]
  /** identifies the record being viewed; a change resets the user's dismiss preference */
  recordKey?: string
}

/**
 * Global right-side context panel (关联面板).
 * Detail pages/drawers publish related-entity sections; the panel hides itself
 * when no content is published. If the user manually closes the panel, the
 * dismiss preference is kept across re-publishes of the SAME record and reset
 * when a different record is published.
 */
export const useContextStore = defineStore('context', () => {
  const visible = ref(false)
  const title = ref('')
  const subtitle = ref('')
  const sections = ref<ContextSection[]>([])
  const recordKey = ref('')
  const userDismissed = ref(false)

  const hasContent = computed(() => sections.value.length > 0)

  function publish(payload: ContextPayload) {
    const nextKey = payload.recordKey ?? ''
    if (nextKey !== recordKey.value) {
      userDismissed.value = false
    }
    recordKey.value = nextKey
    title.value = payload.title
    subtitle.value = payload.subtitle ?? ''
    sections.value = payload.sections.filter((s) => s.items.length > 0)
    visible.value = !userDismissed.value
  }

  function clear() {
    visible.value = false
    title.value = ''
    subtitle.value = ''
    sections.value = []
    recordKey.value = ''
    userDismissed.value = false
  }

  function toggle() {
    if (!hasContent.value) return
    visible.value = !visible.value
    userDismissed.value = !visible.value
  }

  function close() {
    visible.value = false
    userDismissed.value = hasContent.value
  }

  return { visible, title, subtitle, sections, recordKey, userDismissed, hasContent, publish, clear, toggle, close }
})
