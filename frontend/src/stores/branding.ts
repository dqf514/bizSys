import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getBranding } from '@/api/settings'

/** 品牌信息（系统名称/Logo/企微开关）：登录页与外壳共用，登录后缓存复用 */
export const useBrandingStore = defineStore('branding', () => {
  const siteName = ref('')
  const logoUrl = ref('')
  const wecomEnabled = ref(false)
  const loaded = ref(false)

  async function load(force = false) {
    if (loaded.value && !force) return
    try {
      const b = await getBranding()
      siteName.value = b.siteName || ''
      logoUrl.value = b.logoUrl || ''
      wecomEnabled.value = Boolean(b.wecomEnabled)
      loaded.value = true
    } catch {
      /* 失败回退默认品牌（common.app.short），http 层已提示 */
    }
  }

  function apply(settings: { siteName?: string; logoUrl?: string; wecomEnabled?: boolean }) {
    if (settings.siteName !== undefined) siteName.value = settings.siteName
    if (settings.logoUrl !== undefined) logoUrl.value = settings.logoUrl
    if (settings.wecomEnabled !== undefined) wecomEnabled.value = settings.wecomEnabled
  }

  return { siteName, logoUrl, wecomEnabled, loaded, load, apply }
})
