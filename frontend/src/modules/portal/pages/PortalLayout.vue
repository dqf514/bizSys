<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { portalBranding, portalLogout, portalMe } from '@/api/portal'
import { clearPortalToken, getPortalToken } from '@/api/portalHttp'
import { useBrandingStore } from '@/stores/branding'
import { useThemeStore } from '@/stores/theme'
import { useIsMobile } from '@/composables/useIsMobile'
import type { PortalBranding, PortalPartner } from '@/api/types'
import PortalMobileDock from '../components/PortalMobileDock.vue'

defineOptions({ name: 'PortalLayout' })

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const branding = useBrandingStore()
const theme = useThemeStore()
const { isMobile } = useIsMobile()

const partner = ref<PortalPartner | null>(null)
const loggedIn = ref(Boolean(getPortalToken()))
const site = ref<PortalBranding | null>(null)

const siteName = computed(() => site.value?.siteName || branding.siteName || t('portal.portal.title'))
const logoSrc = computed(() => branding.logoUrl || '')
const scopes = computed(() => (partner.value?.permScope || '').split(',').filter(Boolean))
const hasScope = (scope: string) => scopes.value.includes(scope)

/** 桌面顶栏导航：按登录态与权限范围裁剪 */
const navItems = computed(() => {
  const items = [
    { to: '/portal', labelKey: 'portal.portal.home.title' },
    { to: '/portal/tenders', labelKey: 'portal.portal.tenders' },
  ]
  if (loggedIn.value) {
    if (hasScope('visit')) items.push({ to: '/portal/visits', labelKey: 'portal.portal.visits.navTitle' })
    items.push({ to: '/portal/my', labelKey: 'portal.portal.my' })
    if (hasScope('entrust')) {
      items.push({ to: '/portal/orders', labelKey: 'portal.portal.entrust.navTitle' })
    }
    if (hasScope('staff')) {
      items.push({ to: '/portal/staff', labelKey: 'portal.portal.staff.navTitle' })
    }
  }
  return items
})

const activePath = (to: string) =>
  to === '/portal' ? route.path === '/portal' : route.path.startsWith(to)

function switchLang() {
  theme.setAppLocale(theme.locale === 'zh-CN' ? 'en-US' : 'zh-CN')
}

function goLogin() {
  router.push({ path: '/login', query: { redirect: route.fullPath, tab: 'partner' } })
}

async function loadPartner() {
  loggedIn.value = Boolean(getPortalToken())
  if (!loggedIn.value) {
    partner.value = null
    return
  }
  try {
    partner.value = await portalMe()
  } catch {
    /* token 失效时 portalHttp 已清理并回登录页 */
  }
}

async function doLogout() {
  try {
    await portalLogout()
  } catch {
    /* ignore */
  }
  clearPortalToken()
  partner.value = null
  loggedIn.value = false
  router.replace('/portal')
}

onMounted(async () => {
  void branding.load()
  try {
    site.value = await portalBranding()
  } catch {
    /* 公开信息取不到时用默认站点名 */
  }
  await loadPartner()
})

// 登录页在同一标签页完成登录后回到门户时，重新拉一次账号信息
watch(
  () => route.path,
  () => {
    void loadPartner()
  },
)
</script>

<template>
  <div class="portal-shell">
    <header class="portal-header">
      <router-link to="/portal" class="portal-brand">
        <img v-if="logoSrc" :src="logoSrc" :alt="siteName" class="portal-logo" />
        <span class="portal-site">{{ siteName }}</span>
        <span class="portal-tag">{{ t('portal.portal.title') }}</span>
      </router-link>

      <nav v-if="!isMobile" class="portal-nav">
        <router-link
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="portal-nav-item"
          :class="{ active: activePath(item.to) }"
        >
          {{ t(item.labelKey) }}
        </router-link>
      </nav>

      <div class="portal-user">
        <button class="lang-switch" type="button" @click="switchLang">
          {{ theme.locale === 'zh-CN' ? t('common.lang.enUS') : t('common.lang.zhCN') }}
        </button>
        <template v-if="loggedIn">
          <el-dropdown v-if="!isMobile" trigger="click">
            <span class="portal-company">
              {{ partner?.companyName || '' }}
              <el-icon class="portal-caret"><ArrowDown /></el-icon>
            </span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="router.push('/portal/my')">
                  {{ t('portal.portal.my') }}
                </el-dropdown-item>
                <el-dropdown-item @click="router.push('/portal/progress')">
                  {{ t('portal.portal.progress.navTitle') }}
                </el-dropdown-item>
                <el-dropdown-item divided @click="doLogout">
                  {{ t('portal.portal.logout') }}
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button v-else link type="primary" @click="router.push('/portal/my')">
            {{ t('portal.portal.my') }}
          </el-button>
        </template>
        <template v-else>
          <el-button link type="primary" @click="goLogin">{{ t('portal.portal.login') }}</el-button>
          <el-button
            v-if="!isMobile"
            type="primary"
            size="small"
            @click="router.push('/portal/register')"
          >
            {{ t('portal.portal.register') }}
          </el-button>
        </template>
      </div>
    </header>

    <main class="portal-main">
      <router-view />
    </main>

    <footer class="portal-footer">
      <div class="portal-footer-inner">
        <div class="portal-footer-brand">
          <span class="portal-footer-name">{{ site?.companyName || siteName }}</span>
          <span v-if="site?.address" class="portal-footer-line">{{ site.address }}</span>
          <span v-if="site?.phone" class="portal-footer-line">
            {{ t('portal.portal.footer.phone') }}：{{ site.phone }}
          </span>
          <span v-if="site?.email" class="portal-footer-line">{{ site.email }}</span>
        </div>
        <div class="portal-footer-meta">
          <span v-if="site?.icp">{{ site.icp }}</span>
          <span>© {{ new Date().getFullYear() }} {{ site?.companyName || siteName }}</span>
        </div>
      </div>
    </footer>

    <PortalMobileDock v-if="isMobile" :scopes="scopes" :logged-in="loggedIn" />
  </div>
</template>

<style scoped>
.portal-shell {
  min-height: 100vh;
  background: var(--bs-color-bg-app);
  display: flex;
  flex-direction: column;
}

.portal-header {
  position: sticky;
  top: 0;
  z-index: 20;
  display: flex;
  align-items: center;
  gap: var(--bs-space-6);
  padding: 0 var(--bs-space-6);
  height: var(--bs-layout-topbar-height);
  background: var(--bs-color-bg-surface);
  border-bottom: 1px solid var(--bs-color-border-subtle);
}

.portal-brand {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  text-decoration: none;
  min-width: 0;
}

.portal-logo {
  max-width: 30px;
  max-height: 30px;
  object-fit: contain;
}

.portal-site {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
  color: var(--bs-color-fg-default);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.portal-tag {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-primary);
  border: 1px solid var(--bs-color-primary);
  border-radius: var(--bs-radius-sm);
  padding: 0 var(--bs-space-1);
  white-space: nowrap;
}

.portal-nav {
  display: flex;
  gap: var(--bs-space-4);
  flex: 1;
  overflow-x: auto;
}

.portal-nav-item {
  color: var(--bs-color-fg-secondary);
  text-decoration: none;
  font-size: var(--bs-typography-font-size-sm);
  padding: var(--bs-space-1) var(--bs-space-2);
  border-radius: var(--bs-radius-sm);
  white-space: nowrap;
}

.portal-nav-item.active {
  color: var(--bs-color-primary);
  font-weight: 600;
}

.portal-user {
  display: flex;
  align-items: center;
  gap: var(--bs-space-3);
  margin-left: auto;
}

.portal-company {
  display: inline-flex;
  align-items: center;
  gap: var(--bs-space-1);
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-muted);
  max-width: 220px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;
}

.portal-caret {
  font-size: 12px;
}

.lang-switch {
  border: none;
  background: transparent;
  color: var(--bs-color-fg-link);
  cursor: pointer;
  font-size: var(--bs-typography-font-size-sm);
  white-space: nowrap;
}

.portal-main {
  flex: 1;
  width: 100%;
  max-width: var(--bs-layout-content-max-width);
  margin: 0 auto;
  box-sizing: border-box;
  padding: var(--bs-layout-content-padding);
}

.portal-footer {
  border-top: 1px solid var(--bs-color-border-subtle);
  background: var(--bs-color-bg-surface);
  padding: var(--bs-space-5) var(--bs-space-6);
}

.portal-footer-inner {
  max-width: var(--bs-layout-content-max-width);
  margin: 0 auto;
  display: flex;
  flex-wrap: wrap;
  gap: var(--bs-space-4);
  justify-content: space-between;
  align-items: flex-start;
}

.portal-footer-brand {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-1);
  min-width: 0;
}

.portal-footer-name {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.portal-footer-line {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.portal-footer-meta {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-1);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  text-align: right;
}

@media (max-width: 767px) {
  .portal-header {
    gap: var(--bs-space-2);
    padding: 0 var(--bs-space-3);
  }

  .portal-tag {
    display: none;
  }

  .portal-site {
    font-size: var(--bs-typography-font-size-md);
  }

  .portal-main {
    padding: var(--bs-space-3);
    /* 给底部 Dock 留出空间，避免最后一行被遮住（含全面屏手势条） */
    padding-bottom: calc(
      var(--bs-layout-portal-bottom-nav-height) + env(safe-area-inset-bottom) + var(--bs-space-4)
    );
  }

  .portal-footer {
    padding: var(--bs-space-4) var(--bs-space-3);
  }

  .portal-footer-meta {
    text-align: left;
  }
}
</style>
