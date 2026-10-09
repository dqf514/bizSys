import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { setTokens, clearTokens, getAccessToken, getRefreshToken } from '@/api/http'
import * as authApi from '@/api/auth'
import type { MenuNode, UserProfile } from '@/api/types'
import { resetRoutes } from '@/router'
import { useTabsStore } from './tabs'
import { useThemeStore } from './theme'

function normalizeUser(raw: UserProfile): UserProfile {
  return {
    ...raw,
    deptId: raw.deptId ?? raw.dept_id ?? null,
    deptName: raw.deptName ?? raw.dept_name ?? null,
    perms: raw.perms ?? [],
    roles: raw.roles ?? [],
  }
}

export const useAuthStore = defineStore('auth', () => {
  const token = ref(getAccessToken())
  const refreshToken = ref(getRefreshToken())
  const user = ref<UserProfile | null>(null)
  const perms = ref<string[]>([])
  const menus = ref<MenuNode[]>([])
  const loaded = ref(false)

  const isSuper = computed(() => (user.value?.roles ?? []).includes('super'))
  const isLoggedIn = computed(() => Boolean(token.value))

  function hasPerm(code: string): boolean {
    if (!code) return true
    if (isSuper.value) return true
    return perms.value.includes(code)
  }

  function applySession(data: {
    access_token: string
    refresh_token?: string
    user: UserProfile
    menus?: MenuNode[]
  }) {
    token.value = data.access_token
    if (data.refresh_token) refreshToken.value = data.refresh_token
    setTokens(data.access_token, data.refresh_token)
    user.value = normalizeUser(data.user)
    perms.value = user.value.perms ?? []
    menus.value = data.menus ?? user.value.menus ?? []
    const theme = useThemeStore()
    theme.applyFromPrefs(user.value.prefs)
    loaded.value = true
  }

  async function doLogin(username: string, password: string) {
    const data = await authApi.login(username, password)
    applySession({
      access_token: data.access_token,
      refresh_token: data.refresh_token,
      user: data.user,
    })
    // menus come from /auth/me
    await fetchMe()
  }

  async function doWecomLogin(code: string, state: string) {
    const data = await authApi.wecomCallback(code, state)
    applySession({
      access_token: data.access_token,
      refresh_token: data.refresh_token,
      user: data.user,
    })
    await fetchMe()
  }

  async function fetchMe() {
    const profile = normalizeUser(await authApi.me())
    user.value = profile
    perms.value = profile.perms ?? []
    menus.value = profile.menus ?? []
    const theme = useThemeStore()
    theme.applyFromPrefs(profile.prefs)
    loaded.value = true
    return profile
  }

  async function tryRestore() {
    if (!token.value) return false
    try {
      await fetchMe()
      return true
    } catch {
      clearTokens()
      token.value = ''
      refreshToken.value = ''
      user.value = null
      return false
    }
  }

  async function doLogout() {
    try {
      await authApi.logout(refreshToken.value || undefined)
    } catch {
      /* ignore */
    }
    clearTokens()
    token.value = ''
    refreshToken.value = ''
    user.value = null
    perms.value = []
    menus.value = []
    loaded.value = false
    // drop dynamic routes and tab state so the next session starts clean
    resetRoutes()
    useTabsStore().reset()
  }

  /** sync current theme/locale prefs to server after login */
  async function syncPrefs() {
    const theme = useThemeStore()
    try {
      await authApi.updatePrefs({
        theme: theme.theme,
        locale: theme.locale,
        density: theme.density,
        accent: theme.accent,
      })
    } catch {
      /* optional */
    }
  }

  return {
    token,
    refreshToken,
    user,
    perms,
    menus,
    loaded,
    isSuper,
    isLoggedIn,
    hasPerm,
    doLogin,
    doWecomLogin,
    fetchMe,
    tryRestore,
    doLogout,
    syncPrefs,
    applySession,
  }
})
