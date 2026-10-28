import { describe, expect, it } from 'vitest'
import {
  DEFAULT_DOCK_PATHS,
  DOCK_MAX,
  flattenMenuPages,
  parseDockCsv,
  resolveDockPaths,
  serializeDock,
} from './useDock'
import type { MenuNode } from '@/api/types'

function menu(id: number, path: string, titleKey = ''): MenuNode {
  return {
    id,
    parentId: null,
    name: path,
    titleKey,
    path,
    componentKey: 'x/Y',
    icon: '',
    permission: '',
    menuType: 'menu',
    sort: id,
    visible: 1,
    children: [],
  }
}

function dir(id: number, children: MenuNode[]): MenuNode {
  return { ...menu(id, ''), menuType: 'dir', children }
}

const MENUS: MenuNode[] = [
  menu(1, '/workbench', 'menu.workbench'),
  dir(2, [menu(3, '/approval', 'menu.approval'), menu(4, '/task/tasks')]),
  dir(5, [menu(6, '/contract/contracts'), menu(7, '/oa/apply')]),
]

describe('parseDockCsv', () => {
  it('parses csv, trims, dedups and caps at DOCK_MAX', () => {
    expect(parseDockCsv('/a, /b ,/a,/c,/d,/e')).toEqual(['/a', '/b', '/c', '/d'])
    expect(DOCK_MAX).toBe(4)
  })

  it('drops non-path entries and the reserved center path', () => {
    expect(parseDockCsv('abc,/workbench,/a')).toEqual(['/a'])
  })

  it('treats "-" as explicit empty (user removed all)', () => {
    expect(parseDockCsv('-')).toEqual([])
  })
})

describe('serializeDock', () => {
  it('round-trips through parseDockCsv', () => {
    expect(serializeDock(['/b', '/a', '/b'])).toBe('/b,/a')
  })

  it('uses the "-" sentinel for empty selection', () => {
    expect(serializeDock([])).toBe('-')
  })
})

describe('resolveDockPaths', () => {
  it('falls back to defaults filtered by granted menus when never customized', () => {
    expect(resolveDockPaths(MENUS, undefined)).toEqual(DEFAULT_DOCK_PATHS)
    const noOa = MENUS.map((n) =>
      n.id === 5 ? { ...n, children: n.children!.filter((c) => c.path !== '/oa/apply') } : n,
    )
    expect(resolveDockPaths(noOa, undefined)).toEqual(['/approval', '/task/tasks', '/contract/contracts'])
  })

  it('respects a saved list and filters out lost-permission paths', () => {
    expect(resolveDockPaths(MENUS, '/oa/apply,/approval')).toEqual(['/oa/apply', '/approval'])
    expect(resolveDockPaths(MENUS, '/oa/apply,/gone')).toEqual(['/oa/apply'])
  })

  it('keeps the explicit-empty sentinel empty instead of restoring defaults', () => {
    expect(resolveDockPaths(MENUS, '-')).toEqual([])
  })

  it('allows deep-link pages via extraAllowed (e.g. /approval not in menu tree)', () => {
    const noApproval = MENUS.map((n) =>
      n.id === 2 ? { ...n, children: n.children!.filter((c) => c.path !== '/approval') } : n,
    )
    expect(resolveDockPaths(noApproval, undefined)).toEqual(['/task/tasks', '/contract/contracts', '/oa/apply'])
    expect(resolveDockPaths(noApproval, undefined, ['/approval'])).toEqual(DEFAULT_DOCK_PATHS)
    expect(resolveDockPaths(noApproval, '/approval,/task/tasks', ['/approval'])).toEqual(['/approval', '/task/tasks'])
  })
})

describe('flattenMenuPages', () => {
  it('flattens tree-order page nodes, skipping dirs and invisible menus', () => {
    const tree = [...MENUS, { ...menu(8, '/hidden'), visible: 0 }]
    expect(flattenMenuPages(tree).map((n) => n.path)).toEqual([
      '/workbench',
      '/approval',
      '/task/tasks',
      '/contract/contracts',
      '/oa/apply',
    ])
  })
})
