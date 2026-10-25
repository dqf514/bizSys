import { describe, expect, it } from 'vitest'
import { isSystemZone, splitSystemZone } from './useNavZones'
import type { MenuNode } from '@/api/types'

function dir(id: number, name: string, titleKey = ''): MenuNode {
  return { id, name, titleKey, menuType: 'dir', children: [] } as unknown as MenuNode
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
