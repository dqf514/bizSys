import { request, download, toQuery } from './http'
import type { Customer, ListQuery, OptionItem, PageResult } from './types'

export function listCustomers(params: ListQuery) {
  return request<PageResult<Customer>>({
    url: '/crm/customers',
    method: 'get',
    params: toQuery(params as Record<string, unknown>),
  })
}

export function getCustomer(id: number) {
  return request<Customer>({ url: `/crm/customers/${id}`, method: 'get' })
}

export function createCustomer(data: Partial<Customer>) {
  return request<Customer>({ url: '/crm/customers', method: 'post', data })
}

export function updateCustomer(id: number, data: Partial<Customer>) {
  return request<Customer>({ url: `/crm/customers/${id}`, method: 'put', data })
}

export function deleteCustomer(id: number) {
  return request<void>({ url: `/crm/customers/${id}`, method: 'delete' })
}

export function exportCustomers(params: ListQuery) {
  return download(
    {
      url: '/crm/customers/export',
      method: 'post',
      data: toQuery(params as Record<string, unknown>),
    },
    'customers.xlsx',
  )
}

export function downloadCustomerTemplate() {
  return download({ url: '/crm/customers/template', method: 'get' }, 'customer-template.xlsx')
}

export function importCustomers(file: File) {
  const form = new FormData()
  form.append('file', file)
  return request<void>({ url: '/crm/customers/import', method: 'post', data: form })
}

export function customerOptions(q: string, limit = 20) {
  return request<OptionItem[]>({
    url: '/crm/customers/options',
    method: 'get',
    params: { q, limit },
  })
}
