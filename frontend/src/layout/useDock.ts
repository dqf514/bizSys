import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import * as authApi from '@/api/auth'
import { findMenuNodeByPath } from '@/composables/useShortcuts'
import type { MenuNode } from '@/api/types'

/** Dock 定制弹窗开关：TopBar 头像菜单 / Dock 长按打开 */
export const dockSettingsVisible = ref(false)

export function openDockSettings() {
  dockSettingsVisible.value = true
}

/** 中央工作台按钮固定指向（不受定制影响） */
export const DOCK_CENTER_PATH = '/workbench'
/** 左右各 2 个可定制快捷项 */
export const DOCK_MAX = 4
/** 未定制时的默认快捷项（按权限过滤） */
export const DEFAULT_DOCK_PATHS = ['/approval', '/task/tasks', '/contract/contracts', '/oa/apply']
/**
 * 不占菜单但可上 Dock 的深链页面：路径 → 访问权限/图标/标题。
 * （流程中心并入工作台后 /approval 仅剩深链，菜单树查不到，需按权限码放行）
 */
export const EXTRA_DOCK_PAGES: Record<string, { perm: string; icon: string; titleKey: string }> = {
  '/approval': { perm: 'approval:view', icon: 'Stamp', titleKey: 'menu.approval' },
}
// 与快捷方式同策：用户清空全部时的哨兵，区分「从未定制」
const EMPTY_CSV = '-'

export interface DockItem {
  path: string
  title: string
  icon: string
}

/** 拉平菜单树为可见的页面项（dir/button 剔除，无 path 剔除），保持树序 */
export function flattenMenuPages(nodes: MenuNode[]): MenuNode[] {
  const out: MenuNode[] = []
  const walk = (list: MenuNode[]) => {
    for (const n of list) {
      if (n.menuType === 'menu' && n.path && n.visible !== 0) out.push(n)
      if (n.children?.length) walk(n.children)
    }
  }
  walk(nodes)
  return out
}

/** 解析 prefs 里的 CSV：去重、仅保留绝对路径、最多 DOCK_MAX 个；'-' 哨兵 → 空列表 */
export function parseDockCsv(csv: string): string[] {
  if (csv === EMPTY_CSV) return []
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of csv.split(',')) {
    const path = raw.trim()
    if (!path.startsWith('/') || path === DOCK_CENTER_PATH || seen.has(path)) continue
    seen.add(path)
    out.push(path)
    if (out.length >= DOCK_MAX) break
  }
  return out
}

export function serializeDock(paths: string[]): string {
  const list = parseDockCsv(paths.join(','))
  return list.length ? list.join(',') : EMPTY_CSV
}

/**
 * 解析最终展示的快捷路径：
 * - prefs 无 dockShortcuts → 默认项；
 * - 有（含 '-' 哨兵）→ 用户定制列表；
 * 两种情况都按当前权限过滤：菜单树查得到的页面，或 extraAllowed 里的有权限深链页。
 */
export function resolveDockPaths(
  menus: MenuNode[],
  savedCsv: string | undefined,
  extraAllowed: string[] = [],
): string[] {
  const extra = new Set(extraAllowed)
  const candidates = savedCsv === undefined ? DEFAULT_DOCK_PATHS : parseDockCsv(savedCsv)
  return candidates.filter((path) => extra.has(path) || findMenuNodeByPath(menus, path) !== null)
}

/**
 * 底部快捷 Dock 状态。全部派生自 `auth.user.prefs.dockShortcuts`（pinia 单例），
 * Dock、定制弹窗、TopBar 头像菜单响应式同步。
 */
export function useDock() {
  const auth = useAuthStore()
  const { t } = useI18n()

  const savedCsv = computed(() => {
    const raw = auth.user?.prefs?.dockShortcuts
    return typeof raw === 'string' ? raw : undefined
  })

  /** 有权限的深链页（不占菜单，如 /approval） */
  const extraAllowed = computed(() =>
    Object.entries(EXTRA_DOCK_PAGES)
      .filter(([, meta]) => auth.hasPerm(meta.perm))
      .map(([path]) => path),
  )

  const paths = computed(() => resolveDockPaths(auth.menus, savedCsv.value, extraAllowed.value))

  const items = computed<DockItem[]>(() =>
    paths.value
      .map((path) => {
        const node = findMenuNodeByPath(auth.menus, path)
        if (node) return { path, title: node.titleKey ? t(node.titleKey) : node.name, icon: node.icon }
        const extra = EXTRA_DOCK_PAGES[path]
        if (extra && extraAllowed.value.includes(path)) {
          return { path, title: t(extra.titleKey), icon: extra.icon }
        }
        return null
      })
      .filter((i): i is DockItem => i !== null),
  )

  const centerItem = computed<DockItem>(() => {
    const node = findMenuNodeByPath(auth.menus, DOCK_CENTER_PATH)
    return {
      path: DOCK_CENTER_PATH,
      title: node ? (node.titleKey ? t(node.titleKey) : node.name) : t('menu.workbench'),
      icon: node?.icon || 'Odometer',
    }
  })

  /** 定制弹窗候选：全部有权限的页面菜单（排除中央工作台位）+ 有权限的深链页 */
  const available = computed<MenuNode[]>(() => {
    const pages = flattenMenuPages(auth.menus).filter((n) => n.path !== DOCK_CENTER_PATH)
    const extras: MenuNode[] = Object.entries(EXTRA_DOCK_PAGES)
      .filter(([path]) => extraAllowed.value.includes(path))
      .map(
        ([path, meta], i) =>
          ({
            id: -(i + 1),
            parentId: null,
            name: path,
            titleKey: meta.titleKey,
            path,
            componentKey: '',
            icon: meta.icon,
            permission: meta.perm,
            menuType: 'menu',
            sort: 9999 + i,
            visible: 1,
            children: [],
          }) as MenuNode,
      )
    return [...pages, ...extras]
  })

  async function persist(list: string[]) {
    const csv = serializeDock(list)
    if (auth.user) auth.user.prefs = { ...(auth.user.prefs ?? {}), dockShortcuts: csv }
    await authApi.updatePrefs({ dockShortcuts: csv })
  }

  return { items, centerItem, available, savedCsv, persist }
}
