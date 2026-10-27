<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { portalLogin, portalMe } from '@/api/portal'
import { useBrandingStore } from '@/stores/branding'

defineOptions({ name: 'PortalLogin' })

const { t } = useI18n()
const router = useRouter()
const route = useRoute()
const branding = useBrandingStore()

const siteName = computed(() => branding.siteName || t('portal.portal.title'))
const logoSrc = computed(() => branding.logoUrl || '')

const loading = ref(false)
const form = reactive({ username: '', password: '' })

onMounted(() => void branding.load())

async function doLogin() {
  if (!form.username.trim() || !form.password) {
    ElMessage.warning(t('common.form.required'))
    return
  }
  loading.value = true
  try {
    await portalLogin(form.username.trim(), form.password)
    await portalMe()
    const redirect = (route.query.redirect as string) || '/portal/tenders'
    router.replace(redirect)
  } catch {
    /* portalHttp notifies */
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="portal-auth-page">
    <div class="portal-auth-card">
      <div class="portal-auth-brand">
        <img v-if="logoSrc" :src="logoSrc" :alt="siteName" class="portal-auth-logo" />
        <h1 class="portal-auth-title">{{ siteName }}</h1>
      </div>
      <p class="portal-auth-sub">{{ t('portal.portal.accountTip') }}</p>
      <el-form class="portal-auth-form" @submit.prevent="doLogin">
        <el-form-item>
          <el-input v-model="form.username" :placeholder="t('portal.portal.username')" size="large" @keyup.enter="doLogin" />
        </el-form-item>
        <el-form-item>
          <el-input
            v-model="form.password"
            type="password"
            show-password
            :placeholder="t('portal.portal.password')"
            size="large"
            @keyup.enter="doLogin"
          />
        </el-form-item>
        <el-button type="primary" size="large" class="portal-auth-btn" :loading="loading" @click="doLogin">
          {{ t('portal.portal.loginBtn') }}
        </el-button>
      </el-form>
      <div class="portal-auth-links">
        <el-button link type="primary" @click="router.push('/portal/register')">
          {{ t('portal.portal.noAccount') }}
        </el-button>
        <el-button link @click="router.push('/portal/tenders')">{{ t('portal.portal.browseTenders') }}</el-button>
        <el-button link class="muted-link" @click="router.push('/login')">
          {{ t('portal.portal.internalEntry') }}
        </el-button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.portal-auth-page {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bs-color-bg-app);
  overflow: auto;
}

.portal-auth-card {
  width: 420px;
  padding: var(--bs-space-8);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-lg);
  background: var(--bs-color-bg-surface);
  box-shadow: var(--bs-shadow-elevation3);
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
}

.portal-auth-brand {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.portal-auth-logo {
  max-width: 36px;
  max-height: 36px;
  object-fit: contain;
}

.portal-auth-links {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.muted-link {
  color: var(--bs-color-fg-muted);
}

@media (max-width: 768px) {
  .portal-auth-card {
    width: calc(100vw - 2 * var(--bs-space-6));
    padding: var(--bs-space-5);
  }
}

.portal-auth-title {
  font-size: var(--bs-typography-font-size-xl);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.portal-auth-sub {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.portal-auth-form {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
}

.portal-auth-btn {
  width: 100%;
}
</style>
