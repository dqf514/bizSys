import { createApp } from 'vue'
import { createPinia } from 'pinia'
import 'element-plus/theme-chalk/dark/css-vars.css'
import App from './App.vue'
import i18n from './i18n'
import router from './router'
import { setupGuards } from './router/guards'
import { permission } from './directives/permission'
import { setupElementPlus } from './plugins/element-plus'
import { setupIcons } from './icons'
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
setupElementPlus(app)
setupIcons(app)

app.directive('permission', permission)

// a11y：Element Plus 图标组件根节点是 <svg> 且默认无 aria-hidden；
// 全局限顶为装饰性图标统一补上，避免读屏器读出无意义 "image"
app.mixin({
  mounted() {
    const el = this.$el
    if (el instanceof SVGElement && !el.hasAttribute('aria-hidden')) {
      el.setAttribute('aria-hidden', 'true')
    }
  },
})

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
