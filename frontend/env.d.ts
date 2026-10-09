/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<Record<string, unknown>, Record<string, unknown>, unknown>
  export default component
}

declare module 'element-plus/dist/locale/zh-cn.mjs' {
  const locale: Record<string, unknown>
  export default locale
}

declare module 'element-plus/dist/locale/en.mjs' {
  const locale: Record<string, unknown>
  export default locale
}
