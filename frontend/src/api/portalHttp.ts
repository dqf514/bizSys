/** 合作方门户独立 http 实例：独立 token（bs.portal_token）、无刷新机制、401 回 /portal/login。 */

import axios, { AxiosError, type AxiosInstance, type AxiosRequestConfig, type AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'
import i18n from '@/i18n'

const PORTAL_TOKEN_KEY = 'bs.portal_token'

export function getPortalToken() {
  return localStorage.getItem(PORTAL_TOKEN_KEY) || ''
}
export function setPortalToken(token: string) {
  localStorage.setItem(PORTAL_TOKEN_KEY, token)
}
export function clearPortalToken() {
  localStorage.removeItem(PORTAL_TOKEN_KEY)
}

function notify(message: string) {
  ElMessage.error(message || i18n.global.t('common.message.operationFailed'))
}

function toLogin() {
  clearPortalToken()
  if (!location.pathname.startsWith('/portal/login')) {
    location.href = '/portal/login'
  }
}

export const portalHttp: AxiosInstance = axios.create({
  baseURL: '/api/v1/portal',
  timeout: 60000,
})

portalHttp.interceptors.request.use((config) => {
  const token = getPortalToken()
  if (token) {
    config.headers = config.headers ?? {}
    ;(config.headers as Record<string, string>).Authorization = `Bearer ${token}`
  }
  return config
})

portalHttp.interceptors.response.use(
  (response: AxiosResponse) => {
    if (response.config.responseType === 'blob') return response
    const data = response.data as { code?: number; message?: string }
    if (data && typeof data === 'object' && 'code' in data) {
      if (data.code === 0) return response
      const msg = data.message || i18n.global.t('common.message.operationFailed')
      notify(msg)
      return Promise.reject(new Error(msg))
    }
    return response
  },
  (error: AxiosError) => {
    const status = error.response?.status
    const payload = error.response?.data as { message?: string; code?: number } | undefined
    if (status === 401) {
      // 账号待审核/停用（96004）要透出文案；token 失效（20001）回登录页
      if (payload?.code === 96004) notify(payload.message || '')
      else if (!error.config?.url?.includes('/auth/login')) toLogin()
      else notify(payload?.message || i18n.global.t('common.message.operationFailed'))
    } else if (payload?.message) {
      notify(payload.message)
    } else {
      notify(i18n.global.t('common.message.networkError'))
    }
    return Promise.reject(error)
  },
)

export async function portalRequest<T>(config: AxiosRequestConfig): Promise<T> {
  const resp = await portalHttp.request<{ code: number; data: T }>(config)
  return (resp.data as { data: T }).data
}

export async function portalDownload(path: string): Promise<void> {
  const resp = await portalHttp.request<Blob>({ url: path, method: 'get', responseType: 'blob' })
  const blob = resp.data as Blob
  if (blob.type && blob.type.includes('json')) {
    notify(i18n.global.t('common.message.operationFailed'))
    return
  }
  const disposition = (resp.headers?.['content-disposition'] as string) || ''
  let fileName = 'attachment'
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition)
  if (match?.[1]) fileName = decodeURIComponent(match[1])
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
