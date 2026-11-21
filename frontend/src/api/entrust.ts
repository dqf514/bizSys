/** 在线任务委托 API（B2）：内部受理台 —— 列表 / 计数 / 详情 / 代提交 / 受理驳回 / 派发任务 / 取消 / 导出。 */

import { request, download, toQuery } from './http'
import type { ListQuery, PageResult, TaskEntrust, TaskEntrustCreate } from './types'

export function listEntrusts(params: ListQuery) {
  return request<PageResult<TaskEntrust>>({
    url: '/task/entrusts',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function entrustCounts() {
  return request<Record<string, number>>({ url: '/task/entrusts/counts', method: 'get' })
}

export function getEntrust(id: number) {
  return request<TaskEntrust>({ url: `/task/entrusts/${id}`, method: 'get' })
}

/** 业务经理代提交客户委托（电话/邮件委托补录） */
export function createEntrust(data: TaskEntrustCreate) {
  return request<TaskEntrust>({ url: '/task/entrusts', method: 'post', data })
}

/** 受理（accept，发号 WT + 抄送业务负责人）或驳回（reject） */
export function reviewEntrust(
  id: number,
  data: {
    action: 'accept' | 'reject'
    comment?: string
    bizOwnerId?: number | null
    bizOwnerName?: string
    handlerId?: number | null
    handlerName?: string
  },
) {
  return request<TaskEntrust>({ url: `/task/entrusts/${id}/review`, method: 'post', data })
}

/** 受理后生成任务草稿 */
export function dispatchEntrust(
  id: number,
  data: {
    ownerId?: number | null
    ownerName?: string
    deptId?: number | null
    deptName?: string
    planFinishDate?: string | null
    comment?: string
  },
) {
  return request<{ entrust: TaskEntrust; taskId: number; taskName: string }>({
    url: `/task/entrusts/${id}/dispatch`,
    method: 'post',
    data,
  })
}

export function cancelEntrust(id: number) {
  return request<TaskEntrust>({ url: `/task/entrusts/${id}/cancel`, method: 'post' })
}

export function exportEntrusts(params: ListQuery) {
  return download(
    {
      url: '/task/entrusts/export',
      method: 'post',
      data: toQuery(params as Record<string, unknown>),
    },
    'entrusts.xlsx',
  )
}
