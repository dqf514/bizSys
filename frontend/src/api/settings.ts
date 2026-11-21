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
  ai: AiSettings
}

export interface AiSettings {
  enabled: boolean
  baseUrl: string
  apiKeySet: boolean
  model: string
  /** 视觉模型（空 = 复用 model），图片类 AI 功能使用 */
  visionModel: string
  timeout: number
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
  ai?: {
    enabled: boolean
    baseUrl: string
    apiKey?: string
    model: string
    visionModel?: string
    timeout: number
  }
}

export interface MessagingTestResult {
  sent: boolean
  mode: 'real' | 'debug'
  debugCode?: string
}

/* ---------- 流程与事件开关（F5） ---------- */

/** 单据类型与审批状态的对应口径 */
export interface AutomationFlowStatuses {
  /** 提交审批后的状态 */
  approving: string
  /** 审批通过后的状态 */
  approved: string
  /** 审批驳回后的状态 */
  rejected: string
  /** 撤回后的状态 */
  withdrawn: string
}

/** 一类单据的流程开关 */
export interface AutomationFlow {
  bizType: string
  /** 后端给的中文名（前端按 bizType 优先取 i18n） */
  label: string
  definitionCode: string
  /** 流程定义是否已配置且启用；未配置时按「人工审核」口径直通 */
  definitionReady: boolean
  definitionName: string
  /** 是否纳入流程驱动（false = 仍走原人工路径） */
  managed: boolean
  switchKey: string
  enabled: boolean
  /** 允许触发提交的前置状态 */
  submitFrom: string[]
  statuses: AutomationFlowStatuses
  submitPerm: string
  note: string
}

/** 一条事件联动开关 */
export interface AutomationEventSwitch {
  key: string
  name: string
  /** 关键联动：异常会回滚业务事务 */
  critical: boolean
  enabled: boolean
}

/** 一类业务事件及其联动开关 */
export interface AutomationEvent {
  event: string
  label: string
  description: string
  switches: AutomationEventSwitch[]
}

export interface AutomationPanel {
  flows: AutomationFlow[]
  events: AutomationEvent[]
}

export interface AutomationUpdate {
  flows?: { bizType: string; enabled: boolean }[]
  events?: { key: string; enabled: boolean }[]
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

/* ---------- 流程与事件开关（F5） ---------- */

export function getAutomation() {
  return request<AutomationPanel>({ url: '/admin/automation', method: 'get' })
}

export function updateAutomation(data: AutomationUpdate) {
  return request<AutomationPanel>({ url: '/admin/automation', method: 'put', data })
}
