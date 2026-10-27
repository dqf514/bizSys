<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { portalLogin, portalMe } from '@/api/portal'

defineOptions({ name: 'PortalLogin' })

const { t } = useI18n()
const router = useRouter()
const route = useRoute()

const loading = ref(false)
const form = reactive({ username: '', password: '' })

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
      <h1 class="portal-auth-title">{{ t('portal.portal.title') }}</h1>
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
      <el-button link type="primary" @click="router.push('/portal/register')">
        {{ t('portal.portal.noAccount') }}
      </el-button>
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
