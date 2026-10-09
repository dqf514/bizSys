import type { Router } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { useTabsStore } from '@/stores/tabs'
import { registerMenuRoutes, isRoutesRegistered } from './index'

const PUBLIC_PATHS = ['/login']

export function setupGuards(router: Router) {
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
        // retry navigation so newly added routes can match
        return { ...to, replace: true }
      } catch {
        auth.token = ''
        return { path: '/login', query: { redirect: to.fullPath } }
      }
    }

    return true
  })

  router.afterEach((to) => {
    if (to.path.startsWith('/login')) return
    const tabs = useTabsStore()
    tabs.openFromRoute(to)
  })
}
