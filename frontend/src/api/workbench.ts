import { request, toQuery } from './http'
import type { ListQuery, NotifyItem, PageResult } from './types'

/** list current user's in-app notifications (`status=unread` filters unread only) */
export function listNotifies(params: ListQuery) {
  return request<PageResult<NotifyItem>>({
    url: '/admin/notifies',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function notifyUnreadCount() {
  return request<{ count: number }>({ url: '/admin/notifies/unread-count', method: 'get' })
}

export function markNotifyRead(id: number) {
  return request<void>({ url: `/admin/notifies/${id}/read`, method: 'post' })
}

export function markAllNotifiesRead() {
  return request<void>({ url: '/admin/notifies/read-all', method: 'post' })
}
