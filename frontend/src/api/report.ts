import { request, download, toQuery } from './http'
import type { ListQuery, PageResult, Report, ReportDetail, ReportItemOption } from './types'

export function listReports(params: ListQuery) {
  return request<PageResult<Report>>({
    url: '/report/reports',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function reportCounts() {
  return request<Record<string, number>>({ url: '/report/reports/counts', method: 'get' })
}

export function reportItemOptions(q?: string, taskId?: number) {
  const params: Record<string, string | number> = {}
  if (q) params.q = q
  if (taskId) params.task_id = taskId
  return request<ReportItemOption[]>({
    url: '/report/reports/item-options',
    method: 'get',
    params,
  })
}

export function uploadReport(itemId: number, file: File) {
  const form = new FormData()
  form.append('item_id', String(itemId))
  form.append('file', file)
  return request<Report>({ url: '/report/reports', method: 'post', data: form })
}

export function submitReport(id: number, comment?: string) {
  return request<{ id: number; status: string }>({
    url: `/report/reports/${id}/submit`,
    method: 'post',
    data: { comment: comment ?? '' },
  })
}

export function sealReport(id: number, comment?: string) {
  return request<{ id: number; status: string; sealTime: string }>({
    url: `/report/reports/${id}/seal`,
    method: 'post',
    data: { comment: comment ?? '' },
  })
}

export function getReport(id: number) {
  return request<ReportDetail>({ url: `/report/reports/${id}`, method: 'get' })
}

export function downloadReport(id: number, pdf: boolean, fileName: string) {
  return download(
    { url: `/report/reports/${id}/download`, method: 'get', params: pdf ? { pdf: 1 } : {} },
    fileName,
  )
}

export function exportReports(params: ListQuery) {
  return download(
    {
      url: '/report/reports/export',
      method: 'get',
      params: toQuery(params as Record<string, unknown>),
    },
    'reports.xlsx',
  )
}
