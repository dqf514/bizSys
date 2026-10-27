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
  faviconUrl: string
  wecom: WecomSettings
  messaging: MessagingSettings
}

export interface EmailSettings {
  host: string
  port: number
  security: 'ssl' | 'starttls' | 'none'
  username: string
  passwordSet: boolean
  sender: string
}

export interface SmsSettings {
  provider: '' | 'aliyun' | 'tencent' | 'huawei' | 'custom_http'
  aliyun: { accessKeyId: string; accessKeySecretSet: boolean; signName: string; templateCode: string }
  tencent: { secretId: string; secretKeySet: boolean; sdkAppId: string; signName: string; templateId: string }
  huawei: { appKey: string; appSecretSet: boolean; sender: string; templateId: string }
  customHttp: { url: string; paramTemplate: string; authHeaderSet: boolean }
}

export interface MessagingSettings {
  email: EmailSettings
  sms: SmsSettings
}

export interface Branding {
  siteName: string
  logoUrl: string
  faviconUrl: string
  wecomEnabled: boolean
  showDemoAccounts: boolean
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
  messaging?: {
    email?: {
      host: string
      port: number
      security: string
      username: string
      password?: string
      sender: string
    }
    sms?: {
      provider: string
      aliyun?: { accessKeyId: string; accessKeySecret?: string; signName: string; templateCode: string }
      tencent?: { secretId: string; secretKey?: string; sdkAppId: string; signName: string; templateId: string }
      huawei?: { appKey: string; appSecret?: string; sender: string; templateId: string }
      customHttp?: { url: string; paramTemplate: string; authHeader?: string }
    }
  }
}

export interface MessagingTestResult {
  sent: boolean
  mode: 'real' | 'debug'
  debugCode?: string
}

export function testMessaging(channel: 'sms' | 'email', target: string) {
  return request<MessagingTestResult>({
    url: '/admin/settings/messaging/test',
    method: 'post',
    data: { channel, target },
  })
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

export function uploadFavicon(file: File) {
  const form = new FormData()
  form.append('file', file)
  return request<{ faviconUrl: string }>({
    url: '/admin/settings/favicon',
    method: 'post',
    data: form,
    headers: { 'Content-Type': 'multipart/form-data' },
  })
}

export function clearFavicon() {
  return request<{ faviconUrl: string }>({ url: '/admin/settings/favicon', method: 'delete' })
}

export function getBranding() {
  return request<Branding>({ url: '/public/branding', method: 'get' })
}
