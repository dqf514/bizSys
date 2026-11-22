/**
 * 合作方门户独立 http 实例。
 *
 * - 独立 token：`bs.portal_token`（access）/ `bs.portal_refresh`（refresh），与内部 token 互不通用；
 * - 单飞刷新：401 且 code=20001 时用 refresh token 换新 access 并**重放一次原请求**，
 *   手机上正在填的报名 / 投标 / 访客预约表单不会因此丢失；
 * - 401 回登录页（合作方 tab）：优先走路由内跳转（保留 SPA 状态），否则整页 replace。
 */

import axios, { AxiosError, type AxiosInstance, type AxiosRequestConfig, type AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'
import i18n from '@/i18n'

const PORTAL_TOKEN_KEY = 'bs.portal_token'
const PORTAL_REFRESH_KEY = 'bs.portal_refresh'
const CODE_AUTH_EXPIRED = 20001
const CODE_ACCOUNT_DISABLED = 96004

export function getPortalToken() {
  return localStorage.getItem(PORTAL_TOKEN_KEY) || ''
}
export function getPortalRefreshToken() {
  return localStorage.getItem(PORTAL_REFRESH_KEY) || ''
}
export function setPortalToken(token: string, refreshToken?: string) {
  localStorage.setItem(PORTAL_TOKEN_KEY, token)
  if (refreshToken) localStorage.setItem(PORTAL_REFRESH_KEY, refreshToken)
}
export function clearPortalToken() {
  localStorage.removeItem(PORTAL_TOKEN_KEY)
  localStorage.removeItem(PORTAL_REFRESH_KEY)
}

/** 由路由层注入的「登录失效」处理（router.replace，避免整页刷新丢状态） */
let unauthorizedHandler: (() => void) | null = null
export function setPortalUnauthorizedHandler(fn: (() => void) | null) {
  unauthorizedHandler = fn
}

function notify(message: string) {
  ElMessage.error(message || i18n.global.t('common.message.operationFailed'))
}

function toLogin() {
  clearPortalToken()
  if (unauthorizedHandler) {
    unauthorizedHandler()
    return
  }
  if (!location.pathname.startsWith('/login')) {
    const redirect = encodeURIComponent(location.pathname + location.search)
    location.replace(`/login?tab=partner&redirect=${redirect}`)
  }
}

let refreshPromise: Promise<string | null> | null = null

async function refreshPortalToken(): Promise<string | null> {
  const refreshToken = getPortalRefreshToken()
  if (!refreshToken) return null
  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        const resp = await axios.post('/api/v1/portal/auth/refresh', { refresh_token: refreshToken })
        const payload = resp.data
        if (payload?.code === 0 && payload.data?.access_token) {
          setPortalToken(payload.data.access_token, payload.data.refresh_token)
          return payload.data.access_token as string
        }
        return null
      } catch {
        return null
      } finally {
        refreshPromise = null
      }
    })()
  }
  return refreshPromise
}

interface RetriableConfig extends AxiosRequestConfig {
  _retried?: boolean
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

async function handleAuthFailure(original: RetriableConfig): Promise<AxiosResponse> {
  const fresh = await refreshPortalToken()
  if (!fresh) {
    toLogin()
    throw new axios.CanceledError('portal session expired')
  }
  original._retried = true
  ;(original.headers as Record<string, string>).Authorization = `Bearer ${fresh}`
  return portalHttp.request(original)
}

portalHttp.interceptors.response.use(
  async (response: AxiosResponse) => {
    const config = response.config as RetriableConfig
    if (response.config.responseType === 'blob') return response
    const data = response.data as { code?: number; message?: string }
    if (data && typeof data === 'object' && 'code' in data) {
      if (data.code === 0) return response
      if (data.code === CODE_AUTH_EXPIRED && !config._retried && !config.url?.includes('/auth/')) {
        return handleAuthFailure(config)
      }
      const msg = data.message || i18n.global.t('common.message.operationFailed')
      notify(msg)
      return Promise.reject(new Error(msg))
    }
    return response
  },
  async (error: AxiosError) => {
    const config = error.config as RetriableConfig | undefined
    const status = error.response?.status
    const payload = error.response?.data as { message?: string; code?: number } | undefined
    if (
      status === 401 &&
      config &&
      !config._retried &&
      !config.url?.includes('/auth/login') &&
      payload?.code !== CODE_ACCOUNT_DISABLED
    ) {
      try {
        return await handleAuthFailure(config)
      } catch (e) {
        return Promise.reject(e)
      }
    }
    if (status === 401) {
      // 账号待审核/停用（96004）要透出文案；其余 401 走刷新或回登录页
      if (payload?.code === CODE_ACCOUNT_DISABLED) notify(payload.message || '')
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

export async function portalDownload(path: string, params?: Record<string, string>): Promise<void> {
  const resp = await portalHttp.request<Blob>({
    url: path,
    method: 'get',
    params,
    responseType: 'blob',
  })
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

/** 取二进制内容（如二维码 SVG），由调用方转成 objectURL 展示 */
export async function portalBlob(path: string, params?: Record<string, string>): Promise<Blob> {
  const resp = await portalHttp.request<Blob>({ url: path, method: 'get', params, responseType: 'blob' })
  return resp.data as Blob
}
