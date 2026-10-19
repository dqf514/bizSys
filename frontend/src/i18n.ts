import { createI18n } from 'vue-i18n'
import zhCN from './locales/zh-CN/common.json'
import zhMenu from './locales/zh-CN/menu.json'
import zhAuth from './locales/zh-CN/auth.json'
import zhWorkbench from './locales/zh-CN/workbench.json'
import zhAdmin from './locales/zh-CN/admin.json'
import zhApproval from './locales/zh-CN/approval.json'
import zhCrm from './locales/zh-CN/crm.json'
import zhContract from './locales/zh-CN/contract.json'
import zhTask from './locales/zh-CN/task.json'
import zhFinance from './locales/zh-CN/finance.json'
import zhReport from './locales/zh-CN/report.json'
import zhSettings from './locales/zh-CN/settings.json'
import zhOa from './locales/zh-CN/oa.json'
import enUS from './locales/en-US/common.json'
import enMenu from './locales/en-US/menu.json'
import enAuth from './locales/en-US/auth.json'
import enWorkbench from './locales/en-US/workbench.json'
import enAdmin from './locales/en-US/admin.json'
import enApproval from './locales/en-US/approval.json'
import enCrm from './locales/en-US/crm.json'
import enContract from './locales/en-US/contract.json'
import enTask from './locales/en-US/task.json'
import enFinance from './locales/en-US/finance.json'
import enReport from './locales/en-US/report.json'
import enSettings from './locales/en-US/settings.json'
import enOa from './locales/en-US/oa.json'

export const LOCALES = ['zh-CN', 'en-US'] as const
export type Locale = (typeof LOCALES)[number]

function pack(
  common: object,
  menu: object,
  auth: object,
  workbench: object,
  admin: object,
  approval: object,
  crm: object,
  contract: object,
  task: object,
  finance: object,
  report: object,
  settings: object,
  oa: object,
) {
  // 代码统一用 `common.xxx` / `menu.xxx` 等命名空间引用，common 必须挂在 common 下
  return { common, menu, auth, workbench, admin, approval, crm, contract, task, finance, report, settings, oa }
}

const messages = {
  'zh-CN': pack(zhCN, zhMenu, zhAuth, zhWorkbench, zhAdmin, zhApproval, zhCrm, zhContract, zhTask, zhFinance, zhReport, zhSettings, zhOa),
  'en-US': pack(enUS, enMenu, enAuth, enWorkbench, enAdmin, enApproval, enCrm, enContract, enTask, enFinance, enReport, enSettings, enOa),
}

export function detectLocale(): Locale {
  const saved = localStorage.getItem('bs.locale')
  if (saved === 'zh-CN' || saved === 'en-US') return saved
  return navigator.language.startsWith('zh') ? 'zh-CN' : 'en-US'
}

const i18n = createI18n({
  legacy: false,
  locale: detectLocale(),
  fallbackLocale: 'zh-CN',
  messages,
  missingWarn: false,
  fallbackWarn: false,
})

export default i18n

export function setLocale(locale: Locale) {
  i18n.global.locale.value = locale
  localStorage.setItem('bs.locale', locale)
  document.documentElement.setAttribute('lang', locale === 'zh-CN' ? 'zh-CN' : 'en-US')
}
