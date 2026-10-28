import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import 'element-plus/theme-chalk/dark/css-vars.css'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import App from './App.vue'
import i18n from './i18n'
import router from './router'
import { setupGuards } from './router/guards'
import { permission } from './directives/permission'
import './styles/tokens.css'
import './styles/element-vars.css'
import './styles/reset.css'
import './styles/motion.css'
import './styles/mobile.css'

const app = createApp(App)
app.use(createPinia())
app.use(i18n)
app.use(router)
setupGuards(router)
app.use(ElementPlus)

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.directive('permission', permission)

// 非路由场景的动态 import 失败兜底（与 router.onError 同策：整页刷新一次）
window.addEventListener('unhandledrejection', (e) => {
  const msg = String(e.reason?.message ?? e.reason ?? '')
  if (
    msg.includes('Failed to fetch dynamically imported module') ||
    msg.includes('error loading dynamically imported module') ||
    msg.includes('Loading chunk')
  ) {
    const key = `bs.chunkReload:${window.location.pathname}`
    if (!sessionStorage.getItem(key)) {
      sessionStorage.setItem(key, '1')
      window.location.reload()
    }
  }
})

app.mount('#app')
