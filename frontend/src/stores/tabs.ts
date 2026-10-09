import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { RouteLocationNormalizedLoaded } from 'vue-router'

export interface TabItem {
  key: string
  path: string
  fullPath: string
  title: string
  titleKey?: string
  icon?: string
  pinned: boolean
  keepAlive: boolean
  componentName?: string
  query?: Record<string, unknown>
  params?: Record<string, unknown>
}

const MAX_TABS = 15
const STORAGE_KEY = 'bs.tabs'

function loadTabs(): { tabs: TabItem[]; active: string } {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw) as { tabs: TabItem[]; active: string }
  } catch {
    /* ignore */
  }
  return { tabs: [], active: '' }
}

function saveTabs(tabs: TabItem[], active: string) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ tabs, active }))
  } catch {
    /* ignore */
  }
}

export const useTabsStore = defineStore('tabs', () => {
  const initial = loadTabs()
  const tabs = ref<TabItem[]>(initial.tabs)
  const active = ref(initial.active)

  const openTabs = computed(() => tabs.value)

  // throttle full sessionStorage serialization (scroll tracking fires often)
  let persistTimer: ReturnType<typeof setTimeout> | null = null
  function persist() {
    if (persistTimer) return
    persistTimer = setTimeout(() => {
      persistTimer = null
      saveTabs(tabs.value, active.value)
    }, 300)
  }
  function persistNow() {
    if (persistTimer) {
      clearTimeout(persistTimer)
      persistTimer = null
    }
    saveTabs(tabs.value, active.value)
  }

  function findIndex(key: string) {
    return tabs.value.findIndex((t) => t.key === key)
  }

  function makeTab(route: RouteLocationNormalizedLoaded): TabItem | null {
    const tabKey = (route.meta?.tabKey as string) || route.path
    const title = (route.meta?.title as string) || route.name?.toString() || route.path
    const titleKey = route.meta?.titleKey as string | undefined
    return {
      key: tabKey,
      path: route.path,
      fullPath: route.fullPath,
      title,
      titleKey,
      icon: route.meta?.icon as string | undefined,
      pinned: Boolean(route.meta?.pinned),
      keepAlive: Boolean(route.meta?.keepAlive),
      componentName: route.meta?.componentName as string | undefined,
      query: { ...(route.query as Record<string, unknown>) },
      params: { ...(route.params as Record<string, unknown>) },
    }
  }

  function openFromRoute(route: RouteLocationNormalizedLoaded) {
    const tab = makeTab(route)
    if (!tab) return
    const idx = findIndex(tab.key)
    if (idx >= 0) {
      const existing = tabs.value[idx]!
      existing.fullPath = route.fullPath
      existing.path = route.path
      existing.query = tab.query
      existing.params = tab.params
    } else {
      // LRU eviction: close oldest non-pinned
      if (tabs.value.length >= MAX_TABS) {
        const victim = tabs.value.find((t) => !t.pinned && t.key !== tab.key)
        if (victim) close(victim.key, false)
        else {
          // all pinned — skip opening beyond limit
          active.value = tab.key
          return
        }
      }
      tabs.value.push(tab)
    }
    active.value = tab.key
    persist()
  }

  function close(key: string, navigateAway = true): boolean {
    const idx = findIndex(key)
    if (idx < 0) return false
    const tab = tabs.value[idx]!
    if (tab.pinned) return false
    tabs.value.splice(idx, 1)
    if (active.value === key && navigateAway) {
      const next = tabs.value[idx] ?? tabs.value[idx - 1] ?? tabs.value[0]
      active.value = next?.key ?? ''
      return true // caller should navigate
    }
    persist()
    return false
  }

  function closeOthers(key: string) {
    tabs.value = tabs.value.filter((t) => t.key === key || t.pinned)
    active.value = key
    persist()
  }

  function closeRight(key: string) {
    const idx = findIndex(key)
    if (idx < 0) return
    tabs.value = tabs.value.filter((t, i) => i <= idx || t.pinned)
    if (!tabs.value.find((t) => t.key === active.value)) {
      active.value = key
    }
    persist()
  }

  function closeAll() {
    tabs.value = tabs.value.filter((t) => t.pinned)
    active.value = tabs.value[0]?.key ?? ''
    persist()
  }

  function reset() {
    tabs.value = []
    active.value = ''
    persistNow()
  }

  function togglePin(key: string) {
    const tab = tabs.value.find((t) => t.key === key)
    if (!tab) return
    tab.pinned = !tab.pinned
    persist()
  }

  function setActive(key: string) {
    active.value = key
    persist()
  }

  function updateScroll(key: string, scroll: number) {
    const tab = tabs.value.find((t) => t.key === key)
    if (tab) {
      ;(tab as TabItem & { scroll?: number }).scroll = scroll
      persist()
    }
  }

  function getScroll(key: string): number {
    const tab = tabs.value.find((t) => t.key === key) as (TabItem & { scroll?: number }) | undefined
    return tab?.scroll ?? 0
  }

  return {
    tabs: openTabs,
    active,
    openFromRoute,
    close,
    closeOthers,
    closeRight,
    closeAll,
    reset,
    togglePin,
    setActive,
    updateScroll,
    getScroll,
    findIndex,
    MAX_TABS,
  }
})
