import type { Router } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useTabsStore } from '@/stores/tabs'
import { clearTokens } from '@/api/http'
import { getPortalToken } from '@/api/portalHttp'
import { registerMenuRoutes, isRoutesRegistered } from './index'

const PUBLIC_PATHS = ['/login']
// 门户公告对外公开：仅「我的参与」需要门户 token，其余 /portal 页面免登录可浏览
const PORTAL_AUTH_REQUIRED = ['/portal/my']

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

    // 合作方门户：公告公开浏览，仅个人工作台需要门户 token
    if (to.path.startsWith('/portal')) {
      if (PORTAL_AUTH_REQUIRED.some((p) => to.path.startsWith(p)) && !getPortalToken()) {
        return { path: '/portal/login', query: { redirect: to.fullPath } }
      }
      return true
    }

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
        // path 字符串里的 query 不会被解析（vue-router 只在 resolve 字符串 fullPath 时才拆），
        // 必须显式带上 query/hash，否则 ?detail= 深链在整页刷新后丢失。
        return { path: to.path, query: to.query, hash: to.hash, replace: true }
      } catch {
        clearTokens()
        auth.token = ''
        return { path: '/login', query: { redirect: to.fullPath } }
      }
    }

    return true
  })

  // 未匹配到任何路由：路径在菜单全集里 → 403（无权限）；否则 → 404
  router.beforeEach((to) => {
    if (to.name !== 'NotFound') return true
    const auth = useAuthStore()
    if (auth.loaded && auth.allMenuPaths.includes(to.path)) {
      return { name: 'Forbidden', query: { path: to.fullPath }, replace: true }
    }
    return true
  })

  router.afterEach((to) => {
    // 导航成功即清除该路径的自动刷新标记，下次发版仍可自愈
    sessionStorage.removeItem(`bs.chunkReload:${to.fullPath}`)
    if (to.path.startsWith('/login') || to.path.startsWith('/portal')) return
    // redirect / NotFound / Forbidden are transient — never open tabs for them
    if (to.meta?.tabless || to.name === 'NotFound' || to.name === 'Forbidden') return
    const tabs = useTabsStore()
    tabs.openFromRoute(to)
  })
}
