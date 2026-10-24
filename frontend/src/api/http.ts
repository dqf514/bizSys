import axios, { AxiosError, type AxiosInstance, type AxiosRequestConfig, type AxiosResponse } from 'axios'
import { ElMessage } from 'element-plus'
import i18n from '@/i18n'

const ACCESS_KEY = 'bs.access_token'
const REFRESH_KEY = 'bs.refresh_token'

export function getAccessToken() {
  return localStorage.getItem(ACCESS_KEY) || ''
}
export function getRefreshToken() {
  return localStorage.getItem(REFRESH_KEY) || ''
}
export function setTokens(access: string, refresh?: string) {
  localStorage.setItem(ACCESS_KEY, access)
  if (refresh) localStorage.setItem(REFRESH_KEY, refresh)
}
export function clearTokens() {
  localStorage.removeItem(ACCESS_KEY)
  localStorage.removeItem(REFRESH_KEY)
}

const CODE_AUTH_EXPIRED = 20001

function notify(message: string) {
  ElMessage.error(message || i18n.global.t('common.message.operationFailed'))
}

export function toQuery(params: Record<string, unknown>): Record<string, string> {
  const out: Record<string, string> = {}
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '') continue
    if (k === 'filters' && typeof v === 'object') {
      for (const [fk, fv] of Object.entries(v as Record<string, unknown>)) {
        if (fv === undefined || fv === null || fv === '') continue
        out[`filters[${fk}]`] = String(fv)
      }
      continue
    }
    if (k === 'range' && typeof v === 'object') {
      for (const [rk, rv] of Object.entries(v as Record<string, unknown>)) {
        if (rv === undefined || rv === null || rv === '') continue
        out[`range[${rk}]`] = String(rv)
      }
      continue
    }
    out[k] = String(v)
  }
  return out
}

let refreshPromise: Promise<string | null> | null = null

async function refreshAccessToken(): Promise<string | null> {
  const refreshToken = getRefreshToken()
  if (!refreshToken) return null
  if (!refreshPromise) {
    refreshPromise = (async () => {
      try {
        const resp = await axios.post('/api/v1/auth/refresh', { refresh_token: refreshToken })
        const payload = resp.data
        if (payload?.code === 0 && payload.data?.access_token) {
          setTokens(payload.data.access_token)
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

export const http: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
})

http.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) {
    config.headers = config.headers ?? {}
    ;(config.headers as Record<string, string>).Authorization = `Bearer ${token}`
  }
  return config
})

type BlobOk = { ok: true; blob: Blob; fileName: string }
type BlobFail = { ok: false; message: string }

function extractEnvelopeMessage(data: unknown): string {
  if (data && typeof data === 'object' && 'message' in data) {
    return String((data as { message: unknown }).message ?? '')
  }
  return ''
}

async function parseBlobResponse(resp: AxiosResponse): Promise<BlobOk | BlobFail> {
  const blob = resp.data as Blob
  const disposition = (resp.headers?.['content-disposition'] as string) || ''
  let fileName = 'export.xlsx'
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition)
  if (match?.[1]) fileName = decodeURIComponent(match[1])
  // error envelope delivered as blob/json
  if (blob.type && blob.type.includes('json')) {
    try {
      const text = await blob.text()
      const json = JSON.parse(text) as { code?: number; message?: string }
      if (json.code !== undefined && json.code !== 0) {
        return { ok: false, message: json.message || i18n.global.t('common.message.operationFailed') }
      }
    } catch {
      /* keep as file */
    }
  }
  return { ok: true, blob, fileName }
}

async function handleAuthFailure(original: RetriableConfig): Promise<AxiosResponse> {
  const fresh = await refreshAccessToken()
  if (!fresh) {
    clearTokens()
    if (!location.pathname.startsWith('/login')) {
      location.href = '/login'
    }
    throw new axios.CanceledError('session expired')
  }
  original._retried = true
  ;(original.headers as Record<string, string>).Authorization = `Bearer ${fresh}`
  return http.request(original)
}

http.interceptors.response.use(
  async (response: AxiosResponse) => {
    const config = response.config as RetriableConfig
    if (response.config.responseType === 'blob') {
      const parsed = await parseBlobResponse(response)
      if (!parsed.ok) {
        notify(parsed.message)
        return Promise.reject(new Error(parsed.message))
      }
      return response
    }
    const data = response.data as { code?: number; message?: string }
    if (data && typeof data === 'object' && 'code' in data) {
      if (data.code === 0) return response
      if (data.code === CODE_AUTH_EXPIRED && !config._retried) {
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
    if (status === 401 && config && !config._retried && !config.url?.includes('/auth/login')) {
      try {
        return await handleAuthFailure(config)
      } catch (e) {
        return Promise.reject(e)
      }
    }
    if (error.response?.config?.responseType === 'blob') {
      notify(i18n.global.t('common.message.operationFailed'))
      return Promise.reject(error)
    }
    const payload = error.response?.data as { message?: string; code?: number } | undefined
    if (status === 404) {
      notify(payload?.message || i18n.global.t('common.message.loadFailed'))
    } else if (status === 403) {
      // 20007 step-up 需要把后端文案透出（引导二次验证），其余 403 统一友好文案、权限码不外抛
      if (payload?.code === 20007) notify(payload.message || '')
      else notify(i18n.global.t('common.message.noPermission'))
    } else if (payload?.message) {
      notify(payload.message)
    } else if (status === 0 || !error.response) {
      notify(i18n.global.t('common.message.networkError'))
    } else {
      notify(extractEnvelopeMessage(error.response?.data) || i18n.global.t('common.message.operationFailed'))
    }
    return Promise.reject(error)
  },
)

export async function request<T>(config: AxiosRequestConfig): Promise<T> {
  const resp = await http.request<{ code: number; data: T }>(config)
  return (resp.data as { data: T }).data
}

export async function download(config: AxiosRequestConfig, fallbackName = 'export.xlsx'): Promise<void> {
  const resp = await http.request<Blob>({
    ...config,
    responseType: 'blob',
    headers: { ...(config.headers ?? {}), Accept: 'application/octet-stream' },
  })
  const parsed = await parseBlobResponse(resp as AxiosResponse)
  if (!parsed.ok) {
    notify(parsed.message)
    return
  }
  const url = URL.createObjectURL(parsed.blob)
  const a = document.createElement('a')
  a.href = url
  a.download = parsed.fileName || fallbackName
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}
