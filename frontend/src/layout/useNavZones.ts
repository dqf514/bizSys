import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import * as authApi from '@/api/auth'
import type { MenuNode } from '@/api/types'

/** 导航区排序弹窗开关：TopBar 头像菜单打开 */
export const navSortVisible = ref(false)

export function openNavSort() {
  navSortVisible.value = true
}

/** 分区展开状态记忆键（localStorage，与 bs.navCollapsed 同风格） */
export const NAV_ZONE_OPEN_KEY = 'bs.navZoneOpen'

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
 * 路径是否落在该节点（含子孙）内。
 * 详情页路径是菜单路径的下一级（如 /contract/contracts/12），按路径分隔符前缀匹配一并算命中。
 */
export function zoneHasPath(node: MenuNode, path: string): boolean {
  if (!path) return false
  if (node.path && (node.path === path || path.startsWith(`${node.path}/`))) return true
  return (node.children ?? []).some((c) => zoneHasPath(c, path))
}

/** 找到包含指定路径的分区（分区自身或其子孙命中即算）；找不到返回 null */
export function findZoneByPath(zones: MenuNode[], path: string): MenuNode | null {
  if (!path) return null
  return zones.find((z) => zoneHasPath(z, path)) ?? null
}

/** 分区内可见叶子菜单数（menuType==='menu' 且 visible!==0），用于分区头计数徽标 */
export function countZoneItems(node: MenuNode): number {
  return (node.children ?? []).reduce((sum, c) => {
    if (c.visible === 0) return sum
    if (c.menuType === 'menu') return sum + 1
    if (c.menuType === 'dir') return sum + countZoneItems(c)
    return sum
  }, 0)
}

/**
 * 解析记忆的分区 id。
 * 'none'（用户主动全部收起）/ 非法值 / 不在当前可见分区集合内 → null。
 */
export function parseOpenZoneId(raw: string | null, validIds: number[]): number | null {
  if (!raw || raw === 'none') return null
  const id = Number(raw)
  if (!Number.isFinite(id)) return null
  return validIds.includes(id) ? id : null
}

function readStoredZoneRaw(): string | null {
  try {
    return localStorage.getItem(NAV_ZONE_OPEN_KEY)
  } catch {
    return null
  }
}

/** 记忆的展开分区原始值（尚未与可见分区集合求交集） */
const storedZoneRaw = ref<string | null>(readStoredZoneRaw())
/** 当前展开的分区 id（null = 全部收起）。模块级共享，桌面侧栏与移动抽屉同步。 */
const openZoneId = ref<number | null>(null)
/** 用户是否手动操作过展开状态；false 表示尚未操作，首次按当前路由自动定位 */
const zoneOpenTouched = ref(storedZoneRaw.value !== null)

function persistOpenZone() {
  const raw = openZoneId.value == null ? 'none' : String(openZoneId.value)
  storedZoneRaw.value = raw
  try {
    localStorage.setItem(NAV_ZONE_OPEN_KEY, raw)
  } catch {
    /* localStorage 不可用时静默降级，功能不受影响 */
  }
}

/**
 * 三区结构：顶层独立菜单（工作台）钉在顶部，顶级业务目录渲染为滚动「区」；
 * 系统管理区固定在导航底部入口，不参与区排序。
 */
export function useNavZones() {
  const auth = useAuthStore()
  const { t } = useI18n()
  const route = useRoute()

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

  /**
   * 展开状态自愈：
   * - 分区集合为空 → 全部收起；
   * - 用户从未操作过 → 默认展开当前路由所在分区（没有则第一个分区）；
   * - 记忆的分区已失效（权限调整/菜单改版）→ 重新定位到当前路由所在分区。
   * 注意：路由变化**不**触发重新展开（按用户选择记住上次展开的分区）。
   */
  watch(
    () => navZoneDirs.value.map((z) => z.id),
    (ids) => {
      if (!ids.length) {
        openZoneId.value = null
        return
      }
      if (!zoneOpenTouched.value) {
        openZoneId.value = findZoneByPath(navZoneDirs.value, route.path)?.id ?? ids[0] ?? null
        persistOpenZone()
        return
      }
      if (openZoneId.value === null) {
        // 首次按记忆值求交集：'none' 表示用户主动收起，保持 null
        openZoneId.value = parseOpenZoneId(storedZoneRaw.value, ids)
        return
      }
      if (!ids.includes(openZoneId.value)) {
        openZoneId.value = findZoneByPath(navZoneDirs.value, route.path)?.id ?? null
        persistOpenZone()
      }
    },
    { immediate: true },
  )

  /** 点击分区头：切换展开；再次点击同一分区则全部收起 */
  function toggleZone(zone: MenuNode) {
    openZoneId.value = openZoneId.value === zone.id ? null : zone.id
    zoneOpenTouched.value = true
    persistOpenZone()
  }

  function isZoneOpen(zone: MenuNode) {
    return openZoneId.value === zone.id
  }

  /** 当前路由是否落在该分区内（分区收起时也要给分区头高亮） */
  function isZoneActive(zone: MenuNode) {
    return zoneHasPath(zone, route.path)
  }

  return {
    topMenus,
    zoneDirs,
    navZoneDirs,
    systemZone,
    zones,
    customOrder,
    validOrder,
    menuTitle,
    persistOrder,
    openZoneId,
    toggleZone,
    isZoneOpen,
    isZoneActive,
  }
}
