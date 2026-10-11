import { watch } from 'vue'
import { useRoute } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useBrandingStore } from '@/stores/branding'
import { isPageRoute, usePageTitle } from './useShortcuts'

/**
 * Keeps document.title in sync as "{siteName}-{pageTitle}".
 * Updates on route change, locale switch and site-name change (settings save).
 * Falls back to the bare site name on login / redirect / NotFound pages,
 * and to the default app name while branding is still loading.
 */
export function useDocumentTitle() {
  const route = useRoute()
  const branding = useBrandingStore()
  const { t } = useI18n()
  const resolvePageTitle = usePageTitle()

  void branding.load()

  watch(
    () => {
      const site = branding.siteName || t('common.app.short')
      const page = isPageRoute(route) ? resolvePageTitle(route.path) : ''
      // unresolved pages (no menu node / meta title) show the site name only
      return page && page !== route.path ? `${site}-${page}` : site
    },
    (title) => {
      document.title = title
    },
    { immediate: true },
  )
}
