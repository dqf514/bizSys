<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { registerMenuRoutes } from '@/router'
import { useThemeStore } from '@/stores/theme'

const { t, locale } = useI18n()
const auth = useAuthStore()
const theme = useThemeStore()
const router = useRouter()
const route = useRoute()

const activeTab = ref('account')
const loading = ref(false)
const form = reactive({ username: 'admin', password: 'Admin@123456' })

async function doLogin() {
  if (!form.username.trim()) {
    ElMessage.warning(t('auth.login.usernameRequired'))
    return
  }
  if (!form.password) {
    ElMessage.warning(t('auth.login.passwordRequired'))
    return
  }
  loading.value = true
  try {
    await auth.doLogin(form.username.trim(), form.password)
    registerMenuRoutes(auth.menus)
    await auth.syncPrefs()
    const redirect = (route.query.redirect as string) || '/workbench'
    router.replace(redirect)
  } catch {
    ElMessage.error(t('auth.login.failed'))
  } finally {
    loading.value = false
  }
}

function wecomPlaceholder() {
  ElMessage.info(t('auth.login.wecomTip'))
}

function switchLang() {
  theme.setAppLocale(locale.value === 'zh-CN' ? 'en-US' : 'zh-CN')
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-head">
        <h1 class="login-title">{{ t('auth.login.title') }}</h1>
        <p class="login-subtitle">{{ t('auth.login.subtitle') }}</p>
      </div>

      <el-tabs v-model="activeTab" class="login-tabs">
        <el-tab-pane :label="t('auth.login.username')" name="account">
          <el-form class="login-form" @submit.prevent="doLogin">
            <el-form-item>
              <el-input
                v-model="form.username"
                :placeholder="t('auth.login.usernamePlaceholder')"
                size="large"
                @keyup.enter="doLogin"
              />
            </el-form-item>
            <el-form-item>
              <el-input
                v-model="form.password"
                type="password"
                show-password
                :placeholder="t('auth.login.passwordPlaceholder')"
                size="large"
                @keyup.enter="doLogin"
              />
            </el-form-item>
            <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="doLogin">
              {{ loading ? t('auth.login.loggingIn') : t('auth.login.submit') }}
            </el-button>
          </el-form>
        </el-tab-pane>
        <el-tab-pane :label="t('auth.login.wecom')" name="wecom">
          <div class="wecom-box">
            <el-button size="large" class="login-btn" @click="wecomPlaceholder">
              {{ t('auth.login.wecom') }}
            </el-button>
            <p class="wecom-tip">{{ t('auth.login.wecomTip') }}</p>
          </div>
        </el-tab-pane>
      </el-tabs>

      <div class="demo-box">
        <div class="demo-title">{{ t('auth.login.demoTitle') }}</div>
        <div class="demo-line">{{ t('auth.login.demoAdmin') }}</div>
        <div class="demo-line">{{ t('auth.login.demoManager') }}</div>
        <div class="demo-line">{{ t('auth.login.demoLeader') }}</div>
      </div>

      <button class="lang-switch" type="button" @click="switchLang">
        {{ theme.locale === 'zh-CN' ? 'English' : '中文' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  position: fixed;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bs-color-bg-app);
  overflow: auto;
}

.login-card {
  width: 420px;
  padding: var(--bs-space-8);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-lg);
  background: var(--bs-color-bg-surface);
  box-shadow: var(--bs-shadow-elevation3);
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-4);
}

.login-title {
  font-size: var(--bs-typography-font-size-xl);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.login-subtitle {
  margin-top: 4px;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.login-form {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-2);
  margin-top: var(--bs-space-3);
}

.login-btn {
  width: 100%;
}

.wecom-box {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--bs-space-3);
  padding: var(--bs-space-6) 0;
}

.wecom-tip {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

.demo-box {
  padding: var(--bs-space-3);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-fill-lighter);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-secondary);
}

.demo-title {
  font-weight: 600;
  margin-bottom: 4px;
  color: var(--bs-color-fg-default);
}

.demo-line {
  line-height: 1.8;
}

.lang-switch {
  align-self: center;
  border: none;
  background: transparent;
  color: var(--bs-color-fg-link);
  cursor: pointer;
  font-size: var(--bs-typography-font-size-sm);
}
</style>
