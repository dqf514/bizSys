import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import * as authApi from '@/api/auth'
import type { MenuNode } from '@/api/types'

/** 导航区排序弹窗开关：SideNav 底部齿轮与 TopBar 头像菜单共用 */
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

/** 三区结构：顶层独立菜单（工作台）钉在顶部，顶级目录渲染为「区」；区序支持 per-user 自定义 */
export function useNavZones() {
  const auth = useAuthStore()
  const { t } = useI18n()

  const visibleTree = computed(() => visibleMenus(auth.menus))
  /** 顶层独立菜单（工作台），不属于任何区，固定最前 */
  const topMenus = computed(() => visibleTree.value.filter((n) => n.menuType === 'menu'))
  /** 顶级目录 = 区（业务系统/OA系统/系统管理）；无权限区已被 visibleMenus 整区剔除 */
  const zoneDirs = computed(() => visibleTree.value.filter((n) => n.menuType === 'dir'))

  function menuTitle(node: MenuNode) {
    return node.titleKey ? t(node.titleKey) : node.name
  }

  /** per-user zone order stored as CSV of menu ids in prefs.navOrder */
  const customOrder = computed<number[]>(() => {
    const raw = auth.user?.prefs?.navOrder
    if (typeof raw !== 'string' || !raw) return []
    return raw
      .split(',')
      .map((s) => Number(s))
      .filter((n) => Number.isFinite(n))
  })

  /**
   * 结构优先：navOrder 是批次A之前的旧数据（含已移动/已删除的顶层业务菜单 id）
   * 或与当前区结构不一致（缺区/多 id）时整体作废，回退默认区序。
   */
  const validOrder = computed<number[]>(() => {
    const order = customOrder.value
    if (!order.length) return []
    const ids = new Set(zoneDirs.value.map((n) => n.id))
    if (order.length !== ids.size || order.some((id) => !ids.has(id))) return []
    return order
  })

  const zones = computed(() => {
    const order = validOrder.value
    if (!order.length) return zoneDirs.value
    const rank = new Map(order.map((id, i) => [id, i]))
    return [...zoneDirs.value].sort((a, b) => (rank.get(a.id) ?? 0) - (rank.get(b.id) ?? 0))
  })

  async function persistOrder(csv: string) {
    await authApi.updatePrefs({ navOrder: csv })
    if (auth.user) auth.user.prefs = { ...(auth.user.prefs ?? {}), navOrder: csv }
  }

  return { topMenus, zoneDirs, zones, customOrder, validOrder, menuTitle, persistOrder }
}
