<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { portalLogout, portalMe } from '@/api/portal'
import { clearPortalToken, getPortalToken } from '@/api/portalHttp'
import { useBrandingStore } from '@/stores/branding'
import { useThemeStore } from '@/stores/theme'
import type { PortalPartner } from '@/api/types'

defineOptions({ name: 'PortalLayout' })

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const branding = useBrandingStore()
const theme = useThemeStore()

const partner = ref<PortalPartner | null>(null)
const loggedIn = computed(() => Boolean(getPortalToken()))
const siteName = computed(() => branding.siteName || t('portal.portal.title'))
const logoSrc = computed(() => branding.logoUrl || '')

onMounted(async () => {
  void branding.load()
  if (!loggedIn.value) return
  try {
    partner.value = await portalMe()
  } catch {
    /* token 失效时 portalHttp 已清理并回登录页 */
  }
})

function switchLang() {
  theme.setAppLocale(theme.locale === 'zh-CN' ? 'en-US' : 'zh-CN')
}

function goLogin() {
  router.push({ path: '/login', query: { redirect: route.fullPath, tab: 'partner' } })
}

async function doLogout() {
  try {
    await portalLogout()
  } catch {
    /* ignore */
  }
  clearPortalToken()
  partner.value = null
  router.replace('/portal/tenders')
}
</script>

<template>
  <div class="portal-shell">
    <header class="portal-header">
      <router-link to="/portal/tenders" class="portal-brand">
        <img v-if="logoSrc" :src="logoSrc" :alt="siteName" class="portal-logo" />
        <span class="portal-site">{{ siteName }}</span>
        <span class="portal-tag">{{ t('portal.portal.title') }}</span>
      </router-link>
      <nav class="portal-nav">
        <router-link
          to="/portal/tenders"
          class="portal-nav-item"
          :class="{ active: route.path.startsWith('/portal/tenders') }"
        >
          {{ t('portal.portal.tenders') }}
        </router-link>
        <router-link
          v-if="loggedIn"
          to="/portal/my"
          class="portal-nav-item"
          :class="{ active: route.path === '/portal/my' }"
        >
          {{ t('portal.portal.my') }}
        </router-link>
      </nav>
      <div class="portal-user">
        <button class="lang-switch" type="button" @click="switchLang">
          {{ theme.locale === 'zh-CN' ? t('common.lang.enUS') : t('common.lang.zhCN') }}
        </button>
        <template v-if="loggedIn">
          <span class="portal-company">{{ partner?.companyName || '' }}</span>
          <el-button link type="primary" @click="doLogout">{{ t('portal.portal.logout') }}</el-button>
        </template>
        <template v-else>
          <el-button link type="primary" @click="goLogin">{{ t('portal.portal.login') }}</el-button>
          <el-button type="primary" size="small" @click="router.push('/portal/register')">
            {{ t('portal.portal.register') }}
          </el-button>
        </template>
      </div>
    </header>
    <main class="portal-main">
      <router-view />
    </main>
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
  display: flex;
  align-items: center;
  gap: var(--bs-space-6);
  padding: 0 var(--bs-space-6);
  height: 56px;
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
  max-width: 32px;
  max-height: 32px;
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
}

.portal-company {
  font-size: var(--bs-typography-font-size-sm);
  color: var(--bs-color-fg-muted);
  max-width: 220px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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
  padding: var(--bs-space-6);
  max-width: 1080px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}

@media (max-width: 768px) {
  .portal-header {
    gap: var(--bs-space-2);
    padding: 0 var(--bs-space-3);
    height: auto;
    min-height: 56px;
    flex-wrap: wrap;
    padding-top: var(--bs-space-1);
    padding-bottom: var(--bs-space-1);
  }

  .portal-tag {
    display: none;
  }

  .portal-nav {
    gap: var(--bs-space-2);
  }

  .portal-company {
    max-width: 120px;
  }

  .portal-main {
    padding: var(--bs-space-3);
  }
}
</style>
