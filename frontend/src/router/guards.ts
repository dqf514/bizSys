import type { Router } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useTabsStore } from '@/stores/tabs'
import { clearTokens } from '@/api/http'
import { registerMenuRoutes, isRoutesRegistered } from './index'

const PUBLIC_PATHS = ['/login']

/** 动态 chunk 加载失败的特征（发版/重启后浏览器仍持有旧模块图时的典型报错） */
function isChunkLoadError(err: unknown): boolean {
  const msg = String((err as Error)?.message ?? err ?? '')
  return (
    msg.includes('Failed to fetch dynamically imported module') ||
    msg.includes('error loading dynamically imported module') ||
    msg.includes('Loading chunk') ||
    msg.includes('Importing a module script failed')
  )
}

/** 一次性自动刷新：旧 chunk 404 时整页刷新拿到新资源；同一路径只试一次，避免死循环 */
function reloadOnce(path: string) {
  const key = `bs.chunkReload:${path}`
  if (sessionStorage.getItem(key)) return
  sessionStorage.setItem(key, '1')
  window.location.reload()
}

export function setupGuards(router: Router) {
  // 懒加载路由组件失败（多见于发版后旧页面未刷新）→ 自动刷新一次
  router.onError((err, to) => {
    if (isChunkLoadError(err)) reloadOnce(to.fullPath || to.path)
  })

  router.beforeEach(async (to) => {
    const auth = useAuthStore()

    if (PUBLIC_PATHS.includes(to.path)) {
      if (auth.isLoggedIn && auth.loaded) {
        return { path: '/' }
      }
      return true
    }

    if (!auth.token) {
      return { path: '/login', query: { redirect: to.fullPath } }
    }

    // ensure profile + menus loaded, dynamic routes registered
    if (!auth.loaded || !isRoutesRegistered()) {
      try {
        if (!auth.loaded) await auth.fetchMe()
        if (auth.menus?.length) registerMenuRoutes(auth.menus)
        else registerMenuRoutes([])
        // retry navigation so newly added routes can match.
        // NOTE: must be path-only — spreading `to` carries name:'NotFound' (catch-all
        // matched first) and named resolution would land on NotFound again.
        return { path: to.fullPath, replace: true }
      } catch {
        clearTokens()
        auth.token = ''
        return { path: '/login', query: { redirect: to.fullPath } }
      }
    }

    return true
  })

  router.afterEach((to) => {
    // 导航成功即清除该路径的自动刷新标记，下次发版仍可自愈
    sessionStorage.removeItem(`bs.chunkReload:${to.fullPath}`)
    if (to.path.startsWith('/login')) return
    // redirect / NotFound are transient — never open tabs for them
    if (to.meta?.tabless || to.name === 'NotFound') return
    const tabs = useTabsStore()
    tabs.openFromRoute(to)
  })
}
