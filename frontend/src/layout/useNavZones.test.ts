import { describe, expect, it } from 'vitest'
import {
  countZoneItems,
  findZoneByPath,
  isSystemZone,
  parseOpenZoneId,
  splitSystemZone,
  zoneHasPath,
} from './useNavZones'
import type { MenuNode } from '@/api/types'

function dir(id: number, name: string, titleKey = '', children: MenuNode[] = []): MenuNode {
  return { id, name, titleKey, menuType: 'dir', children } as unknown as MenuNode
}

function menu(id: number, name: string, path: string, visible = 1): MenuNode {
  return {
    id,
    parentId: null,
    name,
    titleKey: '',
    path,
    componentKey: '',
    icon: '',
    permission: '',
    menuType: 'menu',
    sort: 0,
    visible,
    children: [],
  } as unknown as MenuNode
}

describe('useNavZones system-zone split', () => {
  it('detects the system zone by seed name or titleKey', () => {
    expect(isSystemZone(dir(1, 'System'))).toBe(true)
    expect(isSystemZone(dir(2, 'Renamed', 'menu.system'))).toBe(true)
    expect(isSystemZone(dir(3, 'BizSystem', 'menu.bizSystem'))).toBe(false)
  })

  it('splits system zone out of sortable nav zones', () => {
    const biz = dir(1, 'BizSystem')
    const oa = dir(2, 'OaSystem')
    const sys = dir(3, 'System')
    const { navZones, systemZone } = splitSystemZone([biz, sys, oa])
    expect(systemZone?.id).toBe(3)
    expect(navZones.map((n) => n.id)).toEqual([1, 2])
  })

  it('returns null system zone when user has no admin menus', () => {
    const { navZones, systemZone } = splitSystemZone([dir(1, 'BizSystem')])
    expect(systemZone).toBeNull()
    expect(navZones).toHaveLength(1)
  })
})

describe('useNavZones accordion helpers', () => {
  const biz = dir(1, 'BizSystem', 'menu.bizCenter', [
    dir(10, 'Contracts', 'menu.contract', [
      menu(100, 'ContractList', '/contract/contracts'),
      menu(101, 'ContractCreate', '', 0),
    ]),
    menu(11, 'Projects', '/projects'),
  ])
  const res = dir(2, 'Resources', 'menu.resources', [
    dir(20, 'StockAsset', 'menu.stockAsset', [menu(200, 'StockOrderList', '/procurement/stock-orders')]),
  ])

  it('matches a zone by exact menu path', () => {
    expect(findZoneByPath([biz, res], '/projects')?.id).toBe(1)
    expect(findZoneByPath([biz, res], '/procurement/stock-orders')?.id).toBe(2)
  })

  it('matches detail pages under a menu path', () => {
    expect(findZoneByPath([biz, res], '/contract/contracts/12')?.id).toBe(1)
  })

  it('does not match unrelated paths', () => {
    expect(findZoneByPath([biz, res], '/oa/apply')).toBeNull()
    expect(findZoneByPath([biz, res], '')).toBeNull()
    expect(zoneHasPath(biz, '')).toBe(false)
  })

  it('counts only visible leaf menus inside a zone', () => {
    // 合同目录 1 个可见叶子 + 1 个隐藏权限行 + 直接挂载的项目页 = 2
    expect(countZoneItems(biz)).toBe(2)
    expect(countZoneItems(res)).toBe(1)
    expect(countZoneItems(dir(3, 'Empty'))).toBe(0)
  })

  it('parses the remembered zone id and drops invalid ones', () => {
    expect(parseOpenZoneId('2', [1, 2])).toBe(2)
    expect(parseOpenZoneId('9', [1, 2])).toBeNull()
    expect(parseOpenZoneId('none', [1, 2])).toBeNull()
    expect(parseOpenZoneId(null, [1, 2])).toBeNull()
    expect(parseOpenZoneId('abc', [1, 2])).toBeNull()
  })
})
