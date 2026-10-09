import { request, toQuery } from './http'
import type { ApprovalTask, ApprovalTimeline, ListQuery, PageResult, UserProfile } from './types'

export type ApprovalTab = 'todo' | 'done' | 'initiated'

export function listApprovalTasks(tab: ApprovalTab, params: ListQuery) {
  return request<PageResult<ApprovalTask>>({
    url: '/approval/tasks',
    method: 'get',
    params: toQuery({ ...params, tab } as Record<string, unknown>),
  })
}

export function getTimeline(bizType: string, bizId: number) {
  return request<ApprovalTimeline>({
    url: `/approval/instances/${bizType}/${bizId}/timeline`,
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

/** lightweight user options for transfer / add-sign (fallback to admin users list) */
export type { UserProfile }
