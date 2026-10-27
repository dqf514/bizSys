<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { registerMenuRoutes } from '@/router'
import { useThemeStore } from '@/stores/theme'
import { useBrandingStore } from '@/stores/branding'
import { getCaptcha, mfaSend, wecomQrUrl } from '@/api/auth'
import type { MfaChannel } from '@/api/types'

const { t, locale } = useI18n()
const auth = useAuthStore()
const theme = useThemeStore()
const branding = useBrandingStore()
const router = useRouter()
const route = useRoute()

const activeTab = ref('account')
const loading = ref(false)
const wecomLoading = ref(false)
const form = reactive({ username: '', password: '', captchaText: '' })

const siteName = computed(() => branding.siteName || t('common.app.short'))
const logoSrc = computed(() => branding.logoUrl || '')

// ---- 图形验证码（一次性，任何登录尝试后即失效，失败必须刷新） ----
const captchaId = ref('')
const captchaSvg = ref('')

async function loadCaptcha() {
  try {
    const data = await getCaptcha()
    captchaId.value = data.captchaId
    captchaSvg.value = data.svg
  } catch {
    /* http notifies */
  }
}

// ---- MFA 二步验证 ----
const mfa = reactive({
  active: false,
  token: '',
  channels: [] as MfaChannel[],
  channel: '' as '' | 'sms' | 'email',
  code: '',
  sending: false,
  countdown: 0,
  debugCode: '',
})
let countdownTimer: number | undefined

function startCountdown(seconds: number) {
  mfa.countdown = seconds
  window.clearInterval(countdownTimer)
  countdownTimer = window.setInterval(() => {
    mfa.countdown -= 1
    if (mfa.countdown <= 0) window.clearInterval(countdownTimer)
  }, 1000)
}

onUnmounted(() => window.clearInterval(countdownTimer))

async function afterLogin() {
  registerMenuRoutes(auth.menus)
  await auth.syncPrefs()
  const redirect = (route.query.redirect as string) || '/workbench'
  router.replace(redirect)
}

async function doLogin() {
  if (!form.username.trim()) {
    ElMessage.warning(t('auth.login.usernameRequired'))
    return
  }
  if (!form.password) {
    ElMessage.warning(t('auth.login.passwordRequired'))
    return
  }
  if (!form.captchaText.trim()) {
    ElMessage.warning(t('auth.login.captchaRequired'))
    return
  }
  loading.value = true
  try {
    const data = await auth.doLogin(form.username.trim(), form.password, {
      captchaId: captchaId.value,
      captchaText: form.captchaText.trim(),
    })
    if ('mfaRequired' in data && data.mfaRequired) {
      mfa.active = true
      mfa.token = data.mfaToken
      mfa.channels = data.channels
      mfa.channel = data.channels[0]?.channel ?? ''
      mfa.code = ''
      mfa.debugCode = ''
      return
    }
    await afterLogin()
  } catch {
    /* http notifies；验证码一次性，失败后强制刷新 */
    form.captchaText = ''
    await loadCaptcha()
  } finally {
    loading.value = false
  }
}

async function sendMfaCode() {
  if (!mfa.channel) return
  mfa.sending = true
  try {
    const r = await mfaSend(mfa.token, mfa.channel)
    mfa.debugCode = r.debugCode ?? ''
    startCountdown(r.cooldown || 60)
    ElMessage.success(t('auth.mfa.codeSent'))
  } catch {
    /* http notifies */
  } finally {
    mfa.sending = false
  }
}

async function verifyMfa() {
  if (!/^\d{6}$/.test(mfa.code)) {
    ElMessage.warning(t('auth.mfa.codeRequired'))
    return
  }
  loading.value = true
  try {
    await auth.doMfaVerify(mfa.token, mfa.code)
    await afterLogin()
  } catch {
    /* http notifies；停留在二步验证 */
  } finally {
    loading.value = false
  }
}

function backToPassword() {
  mfa.active = false
  mfa.token = ''
  mfa.code = ''
  mfa.debugCode = ''
  form.captchaText = ''
  void loadCaptcha()
}

async function goWecomQr() {
  wecomLoading.value = true
  try {
    const { url } = await wecomQrUrl(`${window.location.origin}/login`)
    window.location.href = url
  } catch {
    /* http notifies */
    wecomLoading.value = false
  }
}

/** 企微扫码授权后重定向回 /login?code=...&state=... */
async function handleWecomCallback() {
  const code = route.query.code as string
  const state = route.query.state as string
  if (!code || !state) return false
  wecomLoading.value = true
  activeTab.value = 'wecom'
  try {
    await auth.doWecomLogin(code, state)
    await afterLogin()
    return true
  } catch {
    /* http notifies；停留在登录页 */
    return false
  } finally {
    wecomLoading.value = false
  }
}

onMounted(async () => {
  await branding.load()
  await loadCaptcha()
  await handleWecomCallback()
})

function switchLang() {
  theme.setAppLocale(locale.value === 'zh-CN' ? 'en-US' : 'zh-CN')
}
</script>

<template>
  <div class="login-page">
    <div class="login-card">
      <div class="login-head">
        <div class="login-brand">
          <img v-if="logoSrc" :src="logoSrc" :alt="siteName" class="login-logo" />
          <h1 class="login-title">{{ siteName }}</h1>
        </div>
        <p class="login-subtitle">{{ t('auth.login.subtitle') }}</p>
      </div>

      <el-tabs v-if="!mfa.active" v-model="activeTab" class="login-tabs">
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
            <el-form-item>
              <div class="captcha-row">
                <el-input
                  v-model="form.captchaText"
                  :placeholder="t('auth.login.captchaPlaceholder')"
                  size="large"
                  maxlength="4"
                  class="captcha-input"
                  @keyup.enter="doLogin"
                />
                <button
                  type="button"
                  class="captcha-img"
                  :title="t('auth.login.captchaRefresh')"
                  :aria-label="t('auth.login.captchaRefresh')"
                  @click="loadCaptcha"
                  v-html="captchaSvg"
                ></button>
              </div>
            </el-form-item>
            <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="doLogin">
              {{ loading ? t('auth.login.loggingIn') : t('auth.login.submit') }}
            </el-button>
          </el-form>
        </el-tab-pane>
        <el-tab-pane v-if="branding.wecomEnabled" :label="t('auth.login.wecom')" name="wecom">
          <div class="wecom-box">
            <el-button size="large" class="login-btn" :loading="wecomLoading" @click="goWecomQr">
              {{ wecomLoading ? t('auth.login.wecomRedirecting') : t('auth.login.wecomScan') }}
            </el-button>
            <p class="wecom-tip">{{ t('auth.login.wecomScanTip') }}</p>
          </div>
        </el-tab-pane>
      </el-tabs>

      <!-- MFA 二步验证：密码通过后进入 -->
      <div v-else class="mfa-box">
        <h2 class="mfa-title">{{ t('auth.mfa.title') }}</h2>
        <p class="mfa-tip">{{ t('auth.mfa.tip') }}</p>
        <el-radio-group v-model="mfa.channel" class="mfa-channels">
          <el-radio v-for="c in mfa.channels" :key="c.channel" :value="c.channel">
            {{ c.channel === 'sms' ? t('auth.mfa.channelSms') : t('auth.mfa.channelEmail') }}（{{ c.target }}）
          </el-radio>
        </el-radio-group>
        <div class="mfa-code-row">
          <el-input
            v-model="mfa.code"
            :placeholder="t('auth.mfa.codePlaceholder')"
            size="large"
            maxlength="6"
            class="mfa-code-input"
            @keyup.enter="verifyMfa"
          />
          <el-button
            size="large"
            :loading="mfa.sending"
            :disabled="!mfa.channel || mfa.countdown > 0"
            @click="sendMfaCode"
          >
            {{ mfa.countdown > 0 ? t('auth.mfa.resendAfter', { s: mfa.countdown }) : t('auth.mfa.sendCode') }}
          </el-button>
        </div>
        <el-alert
          v-if="mfa.debugCode"
          type="warning"
          :closable="false"
          class="mfa-debug"
          :title="t('auth.mfa.debugTip', { code: mfa.debugCode })"
        />
        <el-button type="primary" size="large" class="login-btn" :loading="loading" @click="verifyMfa">
          {{ t('auth.mfa.verify') }}
        </el-button>
        <el-button link class="mfa-back" @click="backToPassword">{{ t('auth.mfa.back') }}</el-button>
      </div>

      <div v-if="branding.showDemoAccounts" class="demo-box">
        <div class="demo-title">{{ t('auth.login.demoTitle') }}</div>
        <div class="demo-line">{{ t('auth.login.demoAdmin') }}</div>
        <div class="demo-line">{{ t('auth.login.demoManager') }}</div>
        <div class="demo-line">{{ t('auth.login.demoLeader') }}</div>
      </div>

      <button class="lang-switch" type="button" @click="switchLang">
        {{ theme.locale === 'zh-CN' ? t('common.lang.enUS') : t('common.lang.zhCN') }}
      </button>
      <el-button link class="portal-entry" @click="router.push('/portal')">
        {{ t('auth.login.portalEntry') }}
      </el-button>
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

.login-brand {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
}

.login-logo {
  max-width: 36px;
  max-height: 36px;
  object-fit: contain;
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

.captcha-row {
  display: flex;
  align-items: stretch;
  gap: var(--bs-space-2);
  width: 100%;
}

.captcha-input {
  flex: 1;
}

.captcha-img {
  flex: none;
  width: 132px;
  height: 40px;
  padding: 0;
  border: 1px solid var(--bs-color-border-default);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  cursor: pointer;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.mfa-box {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-3);
  margin-top: var(--bs-space-3);
}

.mfa-title {
  margin: 0;
  font-size: var(--bs-typography-font-size-lg);
  color: var(--bs-color-fg-default);
}

.mfa-tip {
  margin: 0;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.mfa-channels {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-1);
  align-items: flex-start;
}

.mfa-code-row {
  display: flex;
  gap: var(--bs-space-2);
}

.mfa-code-input {
  flex: 1;
}

.mfa-debug {
  font-size: var(--bs-typography-font-size-xs);
}

.mfa-back {
  align-self: center;
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

.portal-entry {
  align-self: center;
  color: var(--bs-color-fg-muted);
}
</style>
