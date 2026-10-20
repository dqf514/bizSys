import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getBranding } from '@/api/settings'

const DEFAULT_FAVICON = '/favicon.svg'
const FAVICON_TYPES: Record<string, string> = {
  ico: 'image/x-icon',
  png: 'image/png',
  svg: 'image/svg+xml',
}

/** 动态替换 <link rel="icon">；未设置自定义 favicon 时恢复 index.html 默认 */
function applyFaviconToDocument(url: string) {
  const href = url || DEFAULT_FAVICON
  let link = document.querySelector<HTMLLinkElement>('link[rel="icon"]')
  if (!link) {
    link = document.createElement('link')
    link.rel = 'icon'
    document.head.appendChild(link)
  }
  const ext = href.split('?')[0]?.split('.').pop()?.toLowerCase() ?? ''
  const type = FAVICON_TYPES[ext]
  if (type) link.type = type
  else link.removeAttribute('type')
  // cache-bust so re-uploading a different file under the same URL refreshes the tab icon
  link.href = url ? `${href}?v=${Date.now()}` : href
}

/** 品牌信息（系统名称/Logo/Favicon/企微开关）：登录页与外壳共用，登录后缓存复用 */
export const useBrandingStore = defineStore('branding', () => {
  const siteName = ref('')
  const logoUrl = ref('')
  const faviconUrl = ref('')
  const wecomEnabled = ref(false)
  const showDemoAccounts = ref(false)
  const loaded = ref(false)

  async function load(force = false) {
    if (loaded.value && !force) return
    try {
      const b = await getBranding()
      siteName.value = b.siteName || ''
      logoUrl.value = b.logoUrl || ''
      faviconUrl.value = b.faviconUrl || ''
      wecomEnabled.value = Boolean(b.wecomEnabled)
      showDemoAccounts.value = Boolean(b.showDemoAccounts)
      loaded.value = true
      applyFaviconToDocument(faviconUrl.value)
    } catch {
      /* 失败回退默认品牌（common.app.short），http 层已提示 */
    }
  }

  function apply(settings: {
    siteName?: string
    logoUrl?: string
    faviconUrl?: string
    wecomEnabled?: boolean
    showDemoAccounts?: boolean
  }) {
    if (settings.siteName !== undefined) siteName.value = settings.siteName
    if (settings.logoUrl !== undefined) logoUrl.value = settings.logoUrl
    if (settings.faviconUrl !== undefined) {
      faviconUrl.value = settings.faviconUrl
      applyFaviconToDocument(faviconUrl.value)
    }
    if (settings.wecomEnabled !== undefined) wecomEnabled.value = settings.wecomEnabled
    if (settings.showDemoAccounts !== undefined) showDemoAccounts.value = settings.showDemoAccounts
  }

  return { siteName, logoUrl, faviconUrl, wecomEnabled, showDemoAccounts, loaded, load, apply }
})
