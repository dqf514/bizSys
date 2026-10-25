import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import * as authApi from '@/api/auth'
import type { MenuNode } from '@/api/types'

/** 导航区排序弹窗开关：TopBar 头像菜单打开 */
export const navSortVisible = ref(false)

export function openNavSort() {
  navSortVisible.value = true
}

function visibleMenus(nodes: MenuNode[]): MenuNode[] {
  return nodes
    .filter((n) => n.visible !== 0 && (n.menuType === 'dir' || n.menuType === 'menu'))
    .map((n) => ({ ...n, children: visibleMenus(n.children ?? []) }))
    .filter((n) => n.menuType === 'menu' || (n.children?.length ?? 0) > 0)
    .sort((a, b) => (a.sort ?? 0) - (b.sort ?? 0))
}

/** 系统管理区识别：种子固定 name=System / titleKey=menu.system，两者任一命中即视为系统管理区 */
export function isSystemZone(node: MenuNode): boolean {
  return node.name === 'System' || node.titleKey === 'menu.system'
}

/**
 * 顶级目录拆分为「业务区」（滚动区渲染、可自定义排序）与「系统管理区」（底部固定入口）。
 * 系统管理区最多一个；无权限时整区已被 visibleMenus 剔除，此处返回 null。
 */
export function splitSystemZone(dirs: MenuNode[]): { navZones: MenuNode[]; systemZone: MenuNode | null } {
  const systemZone = dirs.find(isSystemZone) ?? null
  return { navZones: dirs.filter((n) => n !== systemZone), systemZone }
}

/**
 * 三区结构：顶层独立菜单（工作台）钉在顶部，顶级业务目录渲染为滚动「区」；
 * 系统管理区固定在导航底部入口，不参与区排序。
 */
export function useNavZones() {
  const auth = useAuthStore()
  const { t } = useI18n()

  const visibleTree = computed(() => visibleMenus(auth.menus))
  /** 顶层独立菜单（工作台），不属于任何区，固定最前 */
  const topMenus = computed(() => visibleTree.value.filter((n) => n.menuType === 'menu'))
  /** 顶级目录 = 区；无权限区已被 visibleMenus 整区剔除 */
  const zoneDirs = computed(() => visibleTree.value.filter((n) => n.menuType === 'dir'))

  const split = computed(() => splitSystemZone(zoneDirs.value))
  /** 滚动区渲染的业务区（业务系统/OA系统） */
  const navZoneDirs = computed(() => split.value.navZones)
  /** 系统管理区（底部固定入口；无任何系统管理权限时为 null） */
  const systemZone = computed(() => split.value.systemZone)

  function menuTitle(node: MenuNode) {
    return node.titleKey ? t(node.titleKey) : node.name
  }

  /** per-user zone order stored as CSV of menu ids in prefs.navOrder（仅业务区参与） */
  const customOrder = computed<number[]>(() => {
    const raw = auth.user?.prefs?.navOrder
    if (typeof raw !== 'string' || !raw) return []
    return raw
      .split(',')
      .map((s) => Number(s))
      .filter((n) => Number.isFinite(n))
  })

  /**
   * 结构优先：navOrder 是旧数据（含已移动/已删除/已钉底部的菜单 id）
   * 或与当前业务区结构不一致（缺区/多 id）时整体作废，回退默认区序。
   */
  const validOrder = computed<number[]>(() => {
    const order = customOrder.value
    if (!order.length) return []
    const ids = new Set(navZoneDirs.value.map((n) => n.id))
    if (order.length !== ids.size || order.some((id) => !ids.has(id))) return []
    return order
  })

  const zones = computed(() => {
    const order = validOrder.value
    if (!order.length) return navZoneDirs.value
    const rank = new Map(order.map((id, i) => [id, i]))
    return [...navZoneDirs.value].sort((a, b) => (rank.get(a.id) ?? 0) - (rank.get(b.id) ?? 0))
  })

  async function persistOrder(csv: string) {
    await authApi.updatePrefs({ navOrder: csv })
    if (auth.user) auth.user.prefs = { ...(auth.user.prefs ?? {}), navOrder: csv }
  }

  return { topMenus, zoneDirs, navZoneDirs, systemZone, zones, customOrder, validOrder, menuTitle, persistOrder }
}
