import { request, toQuery } from './http'
import type { ListQuery, NotifyCounts, NotifyItem, PageResult } from './types'

/** list current user's in-app notifications (`status=unread` filters unread only) */
export function listNotifies(params: ListQuery) {
  return request<PageResult<NotifyItem>>({
    url: '/admin/notifies',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

/** message-center tab counts: all / unread / per business type */
export function getNotifyCounts() {
  return request<NotifyCounts>({ url: '/admin/notifies/counts', method: 'get' })
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
