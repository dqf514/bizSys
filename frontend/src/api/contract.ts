import { request, download, toQuery } from './http'
import type { Attachment, Contract, ListQuery, OptionItem, PageResult } from './types'

export function listContracts(params: ListQuery) {
  return request<PageResult<Contract>>({
    url: '/contract/contracts',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function getContract(id: number) {
  return request<Contract>({ url: `/contract/contracts/${id}`, method: 'get' })
}

export function createContract(data: Partial<Contract>) {
  return request<Contract>({ url: '/contract/contracts', method: 'post', data })
}

export function updateContract(id: number, data: Partial<Contract>) {
  return request<Contract>({ url: `/contract/contracts/${id}`, method: 'put', data })
}

export function deleteContract(id: number) {
  return request<void>({ url: `/contract/contracts/${id}`, method: 'delete' })
}

export function submitContract(id: number) {
  return request<void>({ url: `/contract/contracts/${id}/submit`, method: 'post' })
}

export function exportContracts(params: ListQuery) {
  return download(
    {
      url: '/contract/contracts/export',
      method: 'post',
      data: toQuery(params as Record<string, unknown>),
    },
    'contracts.xlsx',
  )
}

export function contractOptions(q?: string) {
  return request<OptionItem[]>({
    url: '/contract/contracts/options',
    method: 'get',
    params: q ? { q } : {},
  })
}

export function uploadContractAttachment(contractId: number, file: File) {
  const form = new FormData()
  form.append('file', file)
  return request<Attachment>({
    url: `/contract/contracts/${contractId}/attachments`,
    method: 'post',
    data: form,
  })
}

export function downloadAttachment(fileId: number | string, fileName = 'attachment') {
  return download({ url: `/contract/attachments/${fileId}`, method: 'get' }, fileName)
}
