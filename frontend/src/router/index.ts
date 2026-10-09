import { createRouter, createWebHistory, type RouteRecordRaw } from 'vue-router'
import type { MenuNode } from '@/api/types'

export const componentModules = import.meta.glob('@/modules/*/pages/**/*.vue')

export function resolveComponentKey(componentKey: string): (() => Promise<unknown>) | null {
  if (!componentKey) return null
  const [mod, name] = componentKey.split('/')
  if (!mod || !name) return null
  const path = `/src/modules/${mod}/pages/${name}.vue`
  const loader = componentModules[path]
  if (!loader) {
    console.warn(`[router] component not found for key: ${componentKey} (${path})`)
    return null
  }
  return loader as () => Promise<unknown>
}

function titleFromKey(titleKey: string, fallback: string) {
  return { titleKey, title: fallback }
}

function menuToRoutes(nodes: MenuNode[], out: RouteRecordRaw[] = []) {
  for (const node of nodes) {
    if (node.menuType === 'menu' && node.path && node.componentKey) {
      const comp = resolveComponentKey(node.componentKey)
      if (comp) {
        const name = node.componentKey.split('/')[1] ?? node.name
        out.push({
          path: node.path,
          name,
          component: comp,
          meta: {
            tabKey: node.path,
            titleKey: node.titleKey,
            title: node.name,
            icon: node.icon,
            keepAlive: true,
            componentName: name,
            permission: node.permission,
            menuId: node.id,
          },
        })
      }
    }
    if (node.children?.length) menuToRoutes(node.children, out)
  }
  return out
}

/** Detail / edit routes opened from list pages (not menu nodes) */
export const extraRoutes: RouteRecordRaw[] = [
  {
    path: '/contract/contracts/new',
    name: 'ContractEditNew',
    component: () => import('@/modules/contract/pages/ContractEdit.vue'),
    meta: {
      tabKey: '/contract/contracts/new',
      titleKey: 'contract.contract.create',
      title: 'New Contract',
      keepAlive: false,
      componentName: 'ContractEdit',
    },
  },
  {
    path: '/contract/contracts/:id/edit',
    name: 'ContractEdit',
    component: () => import('@/modules/contract/pages/ContractEdit.vue'),
    meta: {
      tabKey: '/contract/contracts/edit',
      titleKey: 'contract.contract.edit',
      title: 'Edit Contract',
      keepAlive: false,
      componentName: 'ContractEdit',
    },
  },
  {
    path: '/contract/contracts/:id',
    name: 'ContractDetail',
    component: () => import('@/modules/contract/pages/ContractDetail.vue'),
    meta: {
      tabKey: '/contract/contracts/detail',
      titleKey: 'contract.contract.detail',
      title: 'Contract Detail',
      keepAlive: true,
      componentName: 'ContractDetail',
    },
  },
  {
    path: '/task/tasks/new',
    name: 'TaskEditNew',
    component: () => import('@/modules/task/pages/TaskEdit.vue'),
    meta: {
      tabKey: '/task/tasks/new',
      titleKey: 'task.task.create',
      title: 'New Task',
      keepAlive: false,
      componentName: 'TaskEdit',
    },
  },
  {
    path: '/task/tasks/:id/edit',
    name: 'TaskEdit',
    component: () => import('@/modules/task/pages/TaskEdit.vue'),
    meta: {
      tabKey: '/task/tasks/edit',
      titleKey: 'task.task.edit',
      title: 'Edit Task',
      keepAlive: false,
      componentName: 'TaskEdit',
    },
  },
  {
    path: '/task/tasks/:id',
    name: 'TaskDetail',
    component: () => import('@/modules/task/pages/TaskDetail.vue'),
    meta: {
      tabKey: '/task/tasks/detail',
      titleKey: 'task.task.detail',
      title: 'Task Detail',
      keepAlive: true,
      componentName: 'TaskDetail',
    },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'Login',
      component: () => import('@/modules/auth/Login.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      name: 'Shell',
      component: () => import('@/layout/AppShell.vue'),
      redirect: '/workbench',
      children: [],
    },
    {
      path: '/:pathMatch(.*)*',
      name: 'NotFound',
      component: () => import('@/modules/common/NotFound.vue'),
    },
  ],
})

let routesRegistered = false
const registeredNames = new Set<string>()

export function registerMenuRoutes(menus: MenuNode[]) {
  const routes = menuToRoutes(menus)
  for (const r of routes) {
    const name = r.name as string
    if (!router.hasRoute(name)) {
      router.addRoute('Shell', r)
      registeredNames.add(name)
    }
  }
  for (const r of extraRoutes) {
    const name = r.name as string
    if (!router.hasRoute(name)) {
      router.addRoute('Shell', r)
      registeredNames.add(name)
    }
  }
  routesRegistered = true
  return routes
}

export function isRoutesRegistered() {
  return routesRegistered
}

export function resetRoutes() {
  for (const name of registeredNames) {
    if (router.hasRoute(name)) router.removeRoute(name)
  }
  registeredNames.clear()
  routesRegistered = false
}

export { titleFromKey }
export default router
