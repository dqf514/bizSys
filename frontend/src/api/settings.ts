import { request } from './http'

export interface WecomSettings {
  enabled: boolean
  corpId: string
  agentId: string
  secretSet: boolean
  callbackUrl: string
}

export interface SystemSettings {
  siteName: string
  logoUrl: string
  wecom: WecomSettings
}

export interface Branding {
  siteName: string
  logoUrl: string
  wecomEnabled: boolean
}

export interface SystemSettingsUpdate {
  siteName?: string
  wecom?: {
    enabled: boolean
    corpId: string
    agentId: string
    secret?: string
    callbackUrl?: string
  }
}

export function getSettings() {
  return request<SystemSettings>({ url: '/admin/settings', method: 'get' })
}

export function updateSettings(data: SystemSettingsUpdate) {
  return request<SystemSettings>({ url: '/admin/settings', method: 'put', data })
}

export function uploadLogo(file: File) {
  const form = new FormData()
  form.append('file', file)
  return request<{ logoUrl: string }>({
    url: '/admin/settings/logo',
    method: 'post',
    data: form,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function getBranding() {
  return request<Branding>({ url: '/public/branding', method: 'get' })
}
