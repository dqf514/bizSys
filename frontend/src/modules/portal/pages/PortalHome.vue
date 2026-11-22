<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { portalBranding, portalMe, portalProgress } from '@/api/portal'
import { getPortalToken } from '@/api/portalHttp'
import type { PortalBranding, PortalPartner, PortalProgressSummary } from '@/api/types'

defineOptions({ name: 'PortalHome' })

const { t } = useI18n()
const router = useRouter()

const site = ref<PortalBranding | null>(null)
const partner = ref<PortalPartner | null>(null)
const summary = ref<PortalProgressSummary | null>(null)
const loggedIn = ref(Boolean(getPortalToken()))

const scopes = computed(() => (partner.value?.permScope || '').split(',').filter(Boolean))
const hasScope = (scope: string) => scopes.value.includes(scope)

interface ServiceCard {
  to: string
  icon: string
  titleKey: string
  descKey: string
  auth: boolean
  scope?: string
}

const services = computed<ServiceCard[]>(() => {
  const all: ServiceCard[] = [
    {
      to: '/portal/tenders',
      icon: 'Tickets',
      titleKey: 'portal.portal.tenders',
      descKey: 'portal.portal.home.services.tenderDesc',
      auth: false,
    },
    {
      to: '/portal/visits',
      icon: 'Position',
      titleKey: 'portal.portal.visits.navTitle',
      descKey: 'portal.portal.home.services.visitDesc',
      auth: true,
      scope: 'visit',
    },
    {
      to: '/portal/progress',
      icon: 'DataLine',
      titleKey: 'portal.portal.progress.navTitle',
      descKey: 'portal.portal.home.services.progressDesc',
      auth: true,
    },
    {
      to: '/portal/reports',
      icon: 'Document',
      titleKey: 'portal.portal.reports.navTitle',
      descKey: 'portal.portal.home.services.reportDesc',
      auth: true,
    },
    {
      to: '/portal/billing',
      icon: 'Wallet',
      titleKey: 'portal.portal.billing.navTitle',
      descKey: 'portal.portal.home.services.billingDesc',
      auth: true,
    },
    {
      to: '/portal/handovers',
      icon: 'Goods',
      titleKey: 'portal.portal.handovers.navTitle',
      descKey: 'portal.portal.home.services.handoverDesc',
      auth: true,
    },
    {
      to: '/portal/orders',
      icon: 'Memo',
      titleKey: 'portal.portal.entrust.navTitle',
      descKey: 'portal.portal.home.services.entrustDesc',
      auth: true,
      scope: 'entrust',
    },
    {
      to: '/portal/staff',
      icon: 'UserFilled',
      titleKey: 'portal.portal.staff.navTitle',
      descKey: 'portal.portal.home.services.staffDesc',
      auth: true,
      scope: 'staff',
    },
  ]
  return all.filter((s) => {
    if (!s.auth) return true
    if (!loggedIn.value) return false
    if (s.scope) return hasScope(s.scope)
    return true
  })
})

function goLogin() {
  router.push({ path: '/login', query: { redirect: '/portal', tab: 'partner' } })
}

onMounted(async () => {
  try {
    site.value = await portalBranding()
  } catch {
    /* 取不到就隐藏公告条 */
  }
  if (!loggedIn.value) return
  try {
    partner.value = await portalMe()
  } catch {
    /* 失效由 portalHttp 处理 */
  }
  try {
    const p = await portalProgress()
    summary.value = p.summary
  } catch {
    /* 未绑定往来单位时看板无数据 */
  }
})
</script>

<template>
  <div class="portal-home">
    <section class="portal-hero">
      <div class="portal-hero-text">
        <h1 class="portal-hero-title">{{ site?.siteName || t('portal.portal.title') }}</h1>
        <p class="portal-hero-sub">{{ t('portal.portal.home.heroSub') }}</p>
        <div class="portal-hero-actions">
          <el-button type="primary" size="large" @click="router.push('/portal/tenders')">
            {{ t('portal.portal.home.browseTenders') }}
          </el-button>
          <el-button
            v-if="loggedIn && hasScope('visit')"
            size="large"
            @click="router.push('/portal/visits')"
          >
            {{ t('portal.portal.home.bookVisit') }}
          </el-button>
          <el-button v-else-if="!loggedIn" size="large" @click="goLogin">
            {{ t('portal.portal.home.ctaLogin') }}
          </el-button>
        </div>
      </div>
    </section>

    <el-alert
      v-if="site?.notice"
      class="portal-notice"
      type="info"
      :closable="false"
      :title="site.notice"
      show-icon
    />

    <section v-if="loggedIn && summary" class="portal-summary">
      <div class="portal-summary-card">
        <span class="portal-summary-value">{{ summary.entrustCount }}</span>
        <span class="portal-summary-label">{{ t('portal.portal.home.statEntrust') }}</span>
      </div>
      <div class="portal-summary-card">
        <span class="portal-summary-value">{{ summary.taskCount }}</span>
        <span class="portal-summary-label">{{ t('portal.portal.home.statTask') }}</span>
      </div>
      <div class="portal-summary-card">
        <span class="portal-summary-value">{{ summary.settledAmount }}</span>
        <span class="portal-summary-label">{{ t('portal.portal.home.statSettled') }}</span>
      </div>
      <div class="portal-summary-card">
        <span class="portal-summary-value">{{ summary.paidAmount }}</span>
        <span class="portal-summary-label">{{ t('portal.portal.home.statPaid') }}</span>
      </div>
    </section>

    <section class="portal-services">
      <h2 class="portal-section-title">{{ t('portal.portal.home.serviceTitle') }}</h2>
      <div class="portal-service-grid">
        <router-link
          v-for="s in services"
          :key="s.to"
          :to="s.to"
          class="portal-service-card"
        >
          <el-icon class="portal-service-icon"><component :is="s.icon" /></el-icon>
          <span class="portal-service-title">{{ t(s.titleKey) }}</span>
          <span class="portal-service-desc">{{ t(s.descKey) }}</span>
        </router-link>
      </div>
    </section>
  </div>
</template>

<style scoped>
.portal-home {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-5);
}

.portal-hero {
  background: var(--bs-color-bg-surface);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-lg);
  padding: var(--bs-space-8) var(--bs-space-6);
  background-image: linear-gradient(
    135deg,
    var(--bs-color-bg-surface) 0%,
    var(--bs-color-fill-lighter) 100%
  );
}

.portal-hero-title {
  margin: 0 0 var(--bs-space-2);
  font-size: var(--bs-typography-font-size-xxl);
  font-weight: 700;
  color: var(--bs-color-fg-default);
}

.portal-hero-sub {
  margin: 0 0 var(--bs-space-5);
  color: var(--bs-color-fg-secondary);
  font-size: var(--bs-typography-font-size-sm);
  max-width: 640px;
}

.portal-hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bs-space-3);
}

.portal-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: var(--bs-space-3);
}

.portal-summary-card {
  background: var(--bs-color-bg-surface);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  padding: var(--bs-space-4);
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-1);
}

.portal-summary-value {
  font-size: var(--bs-typography-font-size-xl);
  font-weight: 700;
  color: var(--bs-color-primary);
}

.portal-summary-label {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.portal-section-title {
  margin: 0 0 var(--bs-space-3);
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.portal-service-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: var(--bs-space-3);
}

.portal-service-card {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-1);
  padding: var(--bs-space-4);
  background: var(--bs-color-bg-surface);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  text-decoration: none;
  transition: border-color var(--bs-motion-fast) var(--bs-motion-curve);
}

.portal-service-card:active,
.portal-service-card:hover {
  border-color: var(--bs-color-primary);
}

.portal-service-icon {
  font-size: 22px;
  color: var(--bs-color-primary);
}

.portal-service-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.portal-service-desc {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

@media (max-width: 767px) {
  .portal-hero {
    padding: var(--bs-space-5) var(--bs-space-4);
  }

  .portal-hero-title {
    font-size: var(--bs-typography-font-size-xl);
  }

  .portal-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .portal-service-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: var(--bs-space-2);
  }

  .portal-service-card {
    padding: var(--bs-space-3);
  }
}
</style>
