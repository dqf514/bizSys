import { defineStore } from 'pinia'
import { ref, watch } from 'vue'
import { updatePrefs } from '@/api/auth'
import { getAccessToken } from '@/api/http'
import { setLocale, type Locale } from '@/i18n'
import elZhCn from 'element-plus/dist/locale/zh-cn.mjs'
import elEn from 'element-plus/dist/locale/en.mjs'
import { computed } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'brand-smvic'
export type Density = 'comfortable' | 'compact'
export type Accent = 'blue' | 'green' | 'purple' | 'orange' | 'cyan' | 'red'

export const ACCENTS: Accent[] = ['blue', 'green', 'purple', 'orange', 'cyan', 'red']

function readKey<T extends string>(key: string, fallback: T, allowed: readonly T[]): T {
  const v = localStorage.getItem(key)
  return (allowed as readonly string[]).includes(v ?? '') ? (v as T) : fallback
}

export const useThemeStore = defineStore('theme', () => {
  const theme = ref<ThemeMode>(
    readKey('bs.theme', 'light', ['light', 'dark', 'brand-smvic'] as const),
  )
  const density = ref<Density>(
    readKey('bs.density', 'comfortable', ['comfortable', 'compact'] as const),
  )
  const accent = ref<Accent>(readKey('bs.accent', 'blue', ACCENTS as unknown as readonly Accent[]))
  const locale = ref<Locale>(readKey('bs.locale', 'zh-CN', ['zh-CN', 'en-US'] as const))

  const elementLocale = computed(() => (locale.value === 'en-US' ? elEn : elZhCn))

  function applyToDocument() {
    const root = document.documentElement
    root.setAttribute('data-theme', theme.value)
    root.setAttribute('data-density', density.value)
    root.setAttribute('data-accent', accent.value)
    root.classList.toggle('dark', theme.value === 'dark')
  }

  function persistLocal() {
    localStorage.setItem('bs.theme', theme.value)
    localStorage.setItem('bs.density', density.value)
    localStorage.setItem('bs.accent', accent.value)
    localStorage.setItem('bs.locale', locale.value)
  }

  function persistServer() {
    // 未登录（门户/登录页等公开页）不同步服务端偏好，避免 401 被拦截器重定向
    if (!getAccessToken()) return
    void updatePrefs({
      theme: theme.value,
      density: density.value,
      accent: accent.value,
      locale: locale.value,
    }).catch(() => {
      /* prefs sync optional */
    })
  }

  function toggleTheme() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
  }

  function setTheme(next: ThemeMode) {
    theme.value = next
  }

  function setDensity(next: Density) {
    density.value = next
  }

  function setAccent(next: Accent) {
    accent.value = next
  }

  function setAppLocale(next: Locale) {
    locale.value = next
    setLocale(next)
    persistLocal()
    persistServer()
  }

  function applyFromPrefs(prefs: Record<string, unknown> | undefined | null) {
    if (!prefs) return
    if (typeof prefs.theme === 'string') {
      theme.value = (['light', 'dark', 'brand-smvic'] as const).includes(prefs.theme as ThemeMode)
        ? (prefs.theme as ThemeMode)
        : theme.value
    }
    if (typeof prefs.density === 'string') {
      density.value = (['comfortable', 'compact'] as const).includes(prefs.density as Density)
        ? (prefs.density as Density)
        : density.value
    }
    if (typeof prefs.accent === 'string') {
      accent.value = (ACCENTS as unknown as string[]).includes(prefs.accent)
        ? (prefs.accent as Accent)
        : accent.value
    }
    if (typeof prefs.locale === 'string') {
      locale.value = prefs.locale === 'en-US' ? 'en-US' : 'zh-CN'
      setLocale(locale.value)
    }
    applyToDocument()
    persistLocal()
  }

  watch([theme, density, accent], () => {
    applyToDocument()
    persistLocal()
    persistServer()
  })

  return {
    theme,
    density,
    accent,
    locale,
    elementLocale,
    applyToDocument,
    toggleTheme,
    setTheme,
    setDensity,
    setAccent,
    setAppLocale,
    applyFromPrefs,
  }
})
