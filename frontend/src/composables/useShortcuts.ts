import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import * as authApi from '@/api/auth'
import type { MenuNode } from '@/api/types'

export interface Shortcut {
  path: string
  color: string
}

export interface ResolvedShortcut extends Shortcut {
  title: string
}

export const MAX_SHORTCUTS = 12
export const SHORTCUT_PALETTE = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h']
const DEFAULT_COLOR = 'a'
// sentinel for "user removed every shortcut" — distinguishes from "never customized"
const EMPTY_CSV = '-'

/**
 * Shared shortcut-bar state. All state derives from `auth.user.prefs.navShortcuts`
 * (the pinia auth store is a singleton), so every caller — ShortcutBar chips,
 * TopBar star button — stays in sync reactively.
 */
export function useShortcuts() {
  const route = useRoute()
  const router = useRouter()
  const auth = useAuthStore()
  const { t } = useI18n()

  function findMenuNode(nodes: MenuNode[], path: string): MenuNode | null {
    for (const node of nodes) {
      if (node.menuType === 'menu' && node.path === path) return node
      const hit = node.children?.length ? findMenuNode(node.children, path) : null
      if (hit) return hit
    }
    return null
  }

  /** resolved per render so locale switches re-translate automatically */
  function titleFor(path: string): string {
    const node = findMenuNode(auth.menus, path)
    if (node) return node.titleKey ? t(node.titleKey) : node.name
    const meta = router.resolve(path).meta
    const titleKey = meta?.titleKey as string | undefined
    if (titleKey) return t(titleKey)
    return (meta?.title as string) || path
  }

  function parseCsv(csv: string): Shortcut[] {
    return csv
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
      .map((pair) => {
        const idx = pair.lastIndexOf(':')
        const path = idx > 0 ? pair.slice(0, idx) : pair
        const color = idx > 0 ? pair.slice(idx + 1) : DEFAULT_COLOR
        return { path, color: SHORTCUT_PALETTE.includes(color) ? color : DEFAULT_COLOR }
      })
      .filter((s) => s.path.startsWith('/'))
      .slice(0, MAX_SHORTCUTS)
  }

  const savedCsv = computed(() => {
    const raw = auth.user?.prefs?.navShortcuts
    return typeof raw === 'string' ? raw : undefined
  })

  /** in-memory defaults until the user customizes once */
  function seedDefaults(): Shortcut[] {
    const seeds: Shortcut[] = []
    for (const path of ['/workbench', '/approval']) {
      if (findMenuNode(auth.menus, path)) seeds.push({ path, color: DEFAULT_COLOR })
    }
    return seeds
  }

  const shortcuts = computed<ResolvedShortcut[]>(() => {
    const raw = savedCsv.value
    const list = raw === undefined ? seedDefaults() : parseCsv(raw)
    return list.map((s) => ({ ...s, title: titleFor(s.path) }))
  })

  function persist(list: Shortcut[]) {
    const csv = list.length ? list.map((s) => `${s.path}:${s.color}`).join(',') : EMPTY_CSV
    if (auth.user) auth.user.prefs = { ...(auth.user.prefs ?? {}), navShortcuts: csv }
    authApi.updatePrefs({ navShortcuts: csv }).catch(() => {
      /* keep local state; server sync best-effort */
    })
  }

  function mutate(fn: (list: Shortcut[]) => void) {
    const list = shortcuts.value.map(({ path, color }) => ({ path, color }))
    fn(list)
    persist(list.slice(0, MAX_SHORTCUTS))
  }

  /** pages that may be pinned as shortcuts (login / redirect / NotFound excluded) */
  const isEligible = computed(
    () =>
      route.name !== 'NotFound' && !route.meta?.tabless && !route.path.startsWith('/login'),
  )

  const isFavorite = computed(() => shortcuts.value.some((s) => s.path === route.path))

  const canAdd = computed(
    () => isEligible.value && !isFavorite.value && shortcuts.value.length < MAX_SHORTCUTS,
  )

  function add(path: string, color = DEFAULT_COLOR) {
    if (shortcuts.value.length >= MAX_SHORTCUTS) {
      ElMessage.warning(t('common.shortcut.limitTip'))
      return
    }
    if (shortcuts.value.some((s) => s.path === path)) return
    mutate((list) => {
      list.push({ path, color })
    })
  }

  function addCurrent() {
    if (!canAdd.value) return
    add(route.path)
  }

  function remove(path: string) {
    mutate((list) => {
      const i = list.findIndex((s) => s.path === path)
      if (i >= 0) list.splice(i, 1)
    })
  }

  function toggleFavorite() {
    if (!isEligible.value) return
    if (isFavorite.value) remove(route.path)
    else add(route.path)
  }

  function setColor(path: string, color: string) {
    mutate((list) => {
      const target = list.find((s) => s.path === path)
      if (target) target.color = color
    })
  }

  function reorder(from: number, to: number) {
    if (from < 0 || from === to) return
    mutate((list) => {
      const [item] = list.splice(from, 1)
      if (item) list.splice(to, 0, item)
    })
  }

  return {
    shortcuts,
    isEligible,
    isFavorite,
    canAdd,
    addCurrent,
    remove,
    toggleFavorite,
    setColor,
    reorder,
  }
}
