import { request, download, toQuery } from './http'
import type {
  AdminUser,
  AuditLog,
  Dept,
  DictItem,
  DictItemOption,
  DictType,
  FlowDef,
  FlowDefSaveResult,
  ListQuery,
  MenuNode,
  NumberRule,
  PageResult,
  Role,
} from './types'

// ---- users ----
export interface UserOption {
  id: number
  label: string
  sub?: string
}

export function userOptions(q?: string) {
  return request<UserOption[]>({
    url: '/admin/users/options',
    method: 'get',
    params: q ? { q } : {},
  })
}

export function listUsers(params: ListQuery) {
  return request<PageResult<AdminUser>>({
    url: '/admin/users',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function userCounts() {
  return request<Record<string, number>>({ url: '/admin/users/counts', method: 'get' })
}

export function createUser(data: Partial<AdminUser> & { password?: string }) {
  return request<AdminUser>({ url: '/admin/users', method: 'post', data })
}

export function updateUser(id: number, data: Partial<AdminUser>) {
  return request<AdminUser>({ url: `/admin/users/${id}`, method: 'put', data })
}

export function deleteUser(id: number) {
  return request<void>({ url: `/admin/users/${id}`, method: 'delete' })
}

export function resetUserPassword(id: number, password: string) {
  return request<void>({
    url: `/admin/users/${id}/reset-password`,
    method: 'post',
    data: { password },
  })
}

export function exportUsers(params: ListQuery) {
  return download(
    {
      url: '/admin/users/export',
      method: 'post',
      data: toQuery(params as Record<string, unknown>),
    },
    'users.xlsx',
  )
}

// ---- roles ----
export function listRoles(params: ListQuery = {}) {
  return request<PageResult<Role>>({
    url: '/admin/roles',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function createRole(data: Partial<Role>) {
  return request<Role>({ url: '/admin/roles', method: 'post', data })
}

export function updateRole(id: number, data: Partial<Role>) {
  return request<Role>({ url: `/admin/roles/${id}`, method: 'put', data })
}

export function deleteRole(id: number) {
  return request<void>({ url: `/admin/roles/${id}`, method: 'delete' })
}

export function grantRoleMenus(id: number, menuIds: number[]) {
  return request<void>({ url: `/admin/roles/${id}/menus`, method: 'put', data: { menuIds } })
}

// ---- menus ----
export function menuTree(includeButtons = false) {
  return request<MenuNode[]>({
    url: '/admin/menus/tree',
    method: 'get',
    params: includeButtons ? { include_buttons: '1' } : {},
  })
}

export function createMenu(data: Partial<MenuNode>) {
  return request<MenuNode>({ url: '/admin/menus', method: 'post', data })
}

export function updateMenu(id: number, data: Partial<MenuNode>) {
  return request<MenuNode>({ url: `/admin/menus/${id}`, method: 'put', data })
}

export function deleteMenu(id: number) {
  return request<void>({ url: `/admin/menus/${id}`, method: 'delete' })
}

// ---- dict ----
export function dictTypes() {
  return request<DictType[]>({ url: '/admin/dict/types', method: 'get' })
}

export function exportDicts() {
  return download({ url: '/admin/dict/types/export', method: 'get' }, 'dicts.xlsx')
}

export function dictItems(type: string) {
  return request<DictItemOption[]>({
    url: '/admin/dict/items',
    method: 'get',
    params: { type },
  })
}

export function createDictType(data: Partial<DictType>) {
  return request<DictType>({ url: '/admin/dict/types', method: 'post', data })
}

export function createDictItem(data: Partial<DictItem> & { dictTypeCode: string }) {
  return request<DictItem>({ url: '/admin/dict/items', method: 'post', data })
}

export function updateDictItem(id: number, data: Partial<DictItem>) {
  return request<DictItem>({ url: `/admin/dict/items/${id}`, method: 'put', data })
}

export function deleteDictItem(id: number) {
  return request<void>({ url: `/admin/dict/items/${id}`, method: 'delete' })
}

// ---- number rules ----
export function listNumberRules() {
  return request<NumberRule[] | PageResult<NumberRule>>({
    url: '/admin/number-rules',
    method: 'get',
  })
}

export function createNumberRule(data: Partial<NumberRule>) {
  return request<NumberRule>({ url: '/admin/number-rules', method: 'post', data })
}

export function updateNumberRule(id: number, data: Partial<NumberRule>) {
  return request<NumberRule>({ url: `/admin/number-rules/${id}`, method: 'put', data })
}

export function previewNumberRule(data: Partial<NumberRule>) {
  return request<{ preview: string }>({ url: '/admin/number-rules/preview', method: 'post', data })
}

export function resetNumberRule(id: number, value: number) {
  return request<{ period: string; value: number }>({
    url: `/admin/number-rules/${id}/reset`,
    method: 'post',
    data: { value },
  })
}

// ---- audit logs ----
export function listAuditLogs(params: ListQuery) {
  return request<PageResult<AuditLog>>({
    url: '/admin/audit-logs',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function exportAuditLogs(params: ListQuery) {
  return download(
    { url: '/admin/audit-logs/export', method: 'get', params: toQuery(params as Record<string, unknown>) },
    'audit_logs.xlsx',
  )
}

// ---- depts ----
export function listDepts() {
  return request<Dept[] | PageResult<Dept>>({ url: '/admin/depts', method: 'get' })
}

export function exportDepts() {
  return download({ url: '/admin/depts/export', method: 'get' }, 'depts.xlsx')
}

export function createDept(data: Partial<Dept>) {
  return request<Dept>({ url: '/admin/depts', method: 'post', data })
}

export function updateDept(id: number, data: Partial<Dept>) {
  return request<Dept>({ url: `/admin/depts/${id}`, method: 'put', data })
}

/** 部门任职成员（负责人 isLeader / 主部门 isPrimary），供部门管理与组织审批解析 */
export interface DeptMember {
  userId: number
  username: string
  userName: string
  userStatus: string
  isPrimary: number
  isLeader: number
}

export function listDeptMembers(id: number) {
  return request<DeptMember[]>({ url: `/admin/depts/${id}/members`, method: 'get' })
}

export function setDeptMembers(id: number, members: { userId: number; isPrimary: number; isLeader: number }[]) {
  return request<void>({ url: `/admin/depts/${id}/members`, method: 'put', data: { members } })
}

// ---- flow definitions ----
export function listFlowDefs() {
  return request<FlowDef[] | PageResult<FlowDef>>({ url: '/approval/definitions', method: 'get' })
}

export function createFlowDef(data: Partial<FlowDef>) {
  return request<FlowDefSaveResult>({ url: '/approval/definitions', method: 'post', data })
}

export function updateFlowDef(id: number, data: Partial<FlowDef>) {
  return request<FlowDefSaveResult>({ url: `/approval/definitions/${id}`, method: 'put', data })
}

export function deleteFlowDef(id: number) {
  return request<{ disabled?: boolean }>({ url: `/approval/definitions/${id}`, method: 'delete' })
}
