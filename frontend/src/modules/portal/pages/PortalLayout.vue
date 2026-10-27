<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { portalLogout, portalMe } from '@/api/portal'
import { clearPortalToken } from '@/api/portalHttp'
import type { PortalPartner } from '@/api/types'

defineOptions({ name: 'PortalLayout' })

const { t } = useI18n()
const router = useRouter()
const route = useRoute()

const partner = ref<PortalPartner | null>(null)

onMounted(async () => {
  try {
    partner.value = await portalMe()
  } catch {
    /* 401 已由 portalHttp 跳登录 */
  }
})

async function doLogout() {
  try {
    await portalLogout()
  } catch {
    /* ignore */
  }
  clearPortalToken()
  router.replace('/portal/login')
}
</script>

<template>
  <div class="portal-shell">
    <header class="portal-header">
      <div class="portal-brand">{{ t('portal.portal.title') }}</div>
      <nav class="portal-nav">
        <router-link
          to="/portal/tenders"
          class="portal-nav-item"
          :class="{ active: route.path.startsWith('/portal/tenders') }"
        >
          {{ t('portal.portal.tenders') }}
        </router-link>
        <router-link to="/portal/my" class="portal-nav-item" :class="{ active: route.path === '/portal/my' }">
          {{ t('portal.portal.my') }}
        </router-link>
      </nav>
      <div class="portal-user">
        <span class="portal-company">{{ partner?.companyName || '' }}</span>
        <el-button link type="primary" @click="doLogout">{{ t('portal.portal.logout') }}</el-button>
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
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
  color: var(--bs-color-fg-default);
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
}

.portal-main {
  flex: 1;
  padding: var(--bs-space-6);
  max-width: 1080px;
  width: 100%;
  margin: 0 auto;
  box-sizing: border-box;
}
</style>
