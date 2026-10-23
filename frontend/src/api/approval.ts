import { download, request, toQuery } from './http'
import type {
  ApprovalCcItem,
  ApprovalInstanceDetail,
  ApprovalTask,
  ApprovalTimeline,
  FlowNode,
  FlowPreviewResult,
  ListQuery,
  PageResult,
  UserProfile,
} from './types'

export type ApprovalTab = 'todo' | 'done' | 'initiated'

export function listApprovalTasks(tab: ApprovalTab, params: ListQuery) {
  return request<PageResult<ApprovalTask>>({
    url: '/approval/tasks',
    method: 'get',
    params: toQuery({ ...params, tab } as Record<string, unknown>),
  })
}

export function exportApprovalTasks(tab: ApprovalTab) {
  return download({ url: '/approval/tasks/export', method: 'get', params: { tab } }, `approval_${tab}.xlsx`)
}

export function getTimeline(bizType: string, bizId: number) {
  return request<ApprovalTimeline>({
    url: `/approval/instances/${bizType}/${bizId}/timeline`,
    method: 'get',
  })
}

export function getInstance(instanceId: number) {
  return request<ApprovalInstanceDetail>({
    url: `/approval/instances/${instanceId}`,
    method: 'get',
  })
}

export function approveTask(taskId: number, comment: string) {
  return request<void>({
    url: `/approval/tasks/${taskId}/approve`,
    method: 'post',
    data: { comment },
  })
}

export function rejectTask(taskId: number, comment: string) {
  return request<void>({
    url: `/approval/tasks/${taskId}/reject`,
    method: 'post',
    data: { comment },
  })
}

export function transferTask(taskId: number, toUserId: number, comment: string) {
  return request<void>({
    url: `/approval/tasks/${taskId}/transfer`,
    method: 'post',
    data: { toUserId, comment },
  })
}

export function addSignTask(taskId: number, approverId: number, comment: string) {
  return request<void>({
    url: `/approval/tasks/${taskId}/add-sign`,
    method: 'post',
    data: { approverId, comment },
  })
}

export function withdrawInstance(instanceId: number) {
  return request<void>({
    url: `/approval/instances/${instanceId}/withdraw`,
    method: 'post',
  })
}

export function getInstanceTimeline(instanceId: number) {
  return request<ApprovalTimeline>({
    url: `/approval/instances/${instanceId}/timeline`,
    method: 'get',
  })
}

export function listCcItems(params: ListQuery & { unread?: number }) {
  return request<PageResult<ApprovalCcItem>>({
    url: '/approval/cc',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function markCcRead(ccId: number) {
  return request<{ id: number }>({ url: `/approval/cc/${ccId}/read`, method: 'post' })
}

export function previewFlow(
  definitionCode: string,
  variables: Record<string, unknown>,
  nodes?: Partial<FlowNode>[],
) {
  return request<FlowPreviewResult>({
    url: '/approval/preview',
    method: 'post',
    data: { definitionCode, variables, nodes },
  })
}

/** lightweight user options for transfer / add-sign (fallback to admin users list) */
export type { UserProfile }
