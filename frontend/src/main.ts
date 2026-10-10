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

app.mount('#app')
