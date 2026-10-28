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
const year = new Date().getFullYear()

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
    <div class="login-main">
      <!-- 左侧品牌区：深色渐变 + 风洞流线/仪表刻度抽象装饰（纯 SVG/CSS，无外部图片） -->
      <aside class="brand-zone" aria-hidden="false">
        <svg class="brand-deco" viewBox="0 0 800 600" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
          <defs>
            <linearGradient id="streamFade" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0" stop-color="#ffffff" stop-opacity="0" />
              <stop offset="0.5" stop-color="#ffffff" stop-opacity="0.55" />
              <stop offset="1" stop-color="#ffffff" stop-opacity="0" />
            </linearGradient>
          </defs>
          <!-- 测量网格（左下，淡出） -->
          <g class="deco-grid" stroke="#ffffff" stroke-opacity="0.07" stroke-width="1">
            <line v-for="x in 9" :key="`gx${x}`" :x1="x * 90 - 40" y1="330" :x2="x * 90 - 40" y2="620" />
            <line v-for="y in 4" :key="`gy${y}`" x1="0" :y1="330 + y * 70" x2="820" :y2="330 + y * 70" />
          </g>
          <!-- 风洞流线 -->
          <g fill="none" stroke="url(#streamFade)" stroke-width="1.5">
            <path class="streamline" d="M-40 360 C 180 330, 420 392, 840 350" />
            <path class="streamline slow" d="M-40 420 C 200 386, 460 448, 840 404" />
            <path class="streamline" d="M-40 480 C 220 448, 500 506, 840 458" />
            <path class="streamline slow" d="M-40 540 C 240 508, 540 566, 840 512" />
          </g>
          <!-- 仪表刻度环（右侧，精密仪器意象） -->
          <g class="deco-gauge" transform="translate(640 190)">
            <circle r="118" fill="none" stroke="#ffffff" stroke-opacity="0.14" stroke-width="1.5" />
            <circle r="88" fill="none" stroke="#ffffff" stroke-opacity="0.09" stroke-width="1" />
            <g stroke="#ffffff" stroke-opacity="0.35" stroke-width="2">
              <line
                v-for="i in 24"
                :key="`tk${i}`"
                :x1="0"
                :y1="-118"
                :x2="0"
                :y2="i % 6 === 0 ? -102 : -110"
                :transform="`rotate(${i * 15})`"
              />
            </g>
            <path
              d="M -83 83 A 118 118 0 0 1 83 83"
              fill="none"
              stroke="var(--bs-color-brand-primary)"
              stroke-opacity="0.9"
              stroke-width="3"
              stroke-linecap="round"
              class="gauge-arc"
            />
            <circle r="5" fill="#ffffff" fill-opacity="0.8" />
          </g>
        </svg>

        <div class="brand-top">
          <img v-if="logoSrc" :src="logoSrc" :alt="siteName" class="brand-logo" />
          <span class="brand-company">{{ t('auth.login.brandCompany') }}</span>
        </div>

        <div class="brand-center">
          <h1 class="brand-site">{{ siteName }}</h1>
          <div class="brand-rule" />
          <p class="brand-slogan">{{ t('auth.login.brandSlogan') }}</p>
          <p class="brand-tagline">{{ t('auth.login.brandTagline') }}</p>
        </div>

        <div class="brand-bottom" aria-hidden="true">HMVIC DIGITAL PLATFORM</div>
      </aside>

      <!-- 右侧登录区 -->
      <section class="form-zone">
        <div class="brand-strip">
          <img v-if="logoSrc" :src="logoSrc" :alt="siteName" class="brand-strip-logo" />
          <span class="brand-strip-name">{{ t('auth.login.brandCompany') }}</span>
          <span class="brand-strip-site">{{ siteName }}</span>
        </div>

        <div class="login-card">
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
        </div>

        <div class="form-links">
          <button class="lang-switch" type="button" @click="switchLang">
            {{ theme.locale === 'zh-CN' ? t('common.lang.enUS') : t('common.lang.zhCN') }}
          </button>
          <el-button link class="portal-entry" @click="router.push('/portal')">
            {{ t('auth.login.portalEntry') }}
          </el-button>
        </div>
      </section>
    </div>

    <footer class="login-footer">
      <span>{{ t('auth.login.footerCopyright', { year }) }}</span>
      <a class="footer-link" href="https://hmvic.cn" target="_blank" rel="noopener noreferrer">
        {{ t('auth.login.footerWebsite') }} · hmvic.cn
      </a>
    </footer>
  </div>
</template>

<style scoped>
.login-page {
  position: fixed;
  inset: 0;
  display: flex;
  flex-direction: column;
  background: var(--bs-color-bg-app);
  overflow: auto;
}

.login-main {
  flex: 1;
  display: flex;
  min-height: 0;
}

/* ---- 左侧品牌区（始终深色底，文字用固定浅色；渐变随品牌令牌联动） ---- */
.brand-zone {
  position: relative;
  flex: 0 0 58%;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: var(--bs-space-10) var(--bs-space-10) var(--bs-space-6);
  overflow: hidden;
  color: #ffffff;
  background:
    radial-gradient(
      900px 620px at 88% -12%,
      color-mix(in srgb, var(--bs-color-brand-primary) 55%, transparent),
      transparent 62%
    ),
    linear-gradient(
      152deg,
      color-mix(in srgb, var(--bs-color-brand-primary-active) 55%, #0a1120) 0%,
      #0a1120 52%,
      color-mix(in srgb, var(--bs-color-brand-primary-active) 32%, #0a1120) 100%
    );
}

.brand-deco {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.streamline {
  stroke-dasharray: 5 9;
  animation: stream-flow 7s linear infinite;
}

.streamline.slow {
  animation-duration: 11s;
}

@keyframes stream-flow {
  to {
    stroke-dashoffset: -140;
  }
}

.gauge-arc {
  transform-origin: center;
  animation: gauge-swing 9s var(--bs-ease) infinite alternate;
}

@keyframes gauge-swing {
  from {
    transform: rotate(-24deg);
  }
  to {
    transform: rotate(24deg);
  }
}

.brand-top {
  position: relative;
  display: flex;
  align-items: center;
  gap: var(--bs-space-3);
}

.brand-logo {
  width: 40px;
  height: 40px;
  object-fit: contain;
}

.brand-company {
  font-size: var(--bs-typography-font-size-lg);
  font-weight: 600;
  letter-spacing: 0.04em;
}

.brand-center {
  position: relative;
  max-width: 520px;
}

.brand-site {
  margin: 0;
  font-size: 40px;
  font-weight: 650;
  letter-spacing: 0.02em;
  line-height: var(--bs-typography-line-height-tight);
}

.brand-rule {
  width: 56px;
  height: 3px;
  margin: var(--bs-space-5) 0;
  border-radius: var(--bs-radius-full);
  background: var(--bs-color-brand-primary);
}

.brand-slogan {
  margin: 0;
  font-size: var(--bs-typography-font-size-lg);
  color: rgba(255, 255, 255, 0.86);
  line-height: var(--bs-typography-line-height-normal);
}

.brand-tagline {
  margin: var(--bs-space-3) 0 0;
  font-size: var(--bs-typography-font-size-sm);
  color: rgba(255, 255, 255, 0.55);
  letter-spacing: 0.06em;
}

.brand-bottom {
  position: relative;
  font-size: var(--bs-typography-font-size-xs);
  letter-spacing: 0.32em;
  color: rgba(255, 255, 255, 0.32);
}

/* ---- 右侧登录区 ---- */
.form-zone {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--bs-space-4);
  padding: var(--bs-space-6) var(--bs-space-4);
}

.brand-strip {
  display: none;
  align-items: center;
  gap: var(--bs-space-2);
  margin-bottom: var(--bs-space-2);
}

.brand-strip-logo {
  width: 28px;
  height: 28px;
  object-fit: contain;
}

.brand-strip-name {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.brand-strip-site {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.login-card {
  width: 400px;
  max-width: 100%;
  padding: var(--bs-space-8);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-lg);
  background: var(--bs-color-bg-surface);
  box-shadow: var(--bs-shadow-elevation3);
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-4);
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

.form-links {
  display: flex;
  align-items: center;
  gap: var(--bs-space-4);
}

.lang-switch {
  border: none;
  background: transparent;
  color: var(--bs-color-fg-link);
  cursor: pointer;
  font-size: var(--bs-typography-font-size-sm);
}

.portal-entry {
  color: var(--bs-color-fg-muted);
}

/* ---- 页脚 ---- */
.login-footer {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--bs-space-4);
  padding: var(--bs-space-3) var(--bs-space-4);
  border-top: 1px solid var(--bs-color-border-subtle);
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.footer-link {
  color: var(--bs-color-fg-muted);
  text-decoration: none;
}

.footer-link:hover {
  color: var(--bs-color-fg-link);
}

/* ---- 键盘焦点可见 ---- */
.lang-switch:focus-visible,
.captcha-img:focus-visible,
.footer-link:focus-visible {
  outline: 2px solid var(--bs-color-brand-primary);
  outline-offset: 2px;
  border-radius: var(--bs-radius-sm);
}

/* ---- 响应式：窄屏品牌区收为顶部横条 ---- */
@media (max-width: 1024px) {
  .brand-zone {
    flex-basis: 50%;
    padding: var(--bs-space-8) var(--bs-space-8) var(--bs-space-5);
  }

  .brand-site {
    font-size: 32px;
  }
}

@media (max-width: 767px) {
  .brand-zone {
    display: none;
  }

  .brand-strip {
    display: flex;
  }

  .form-zone {
    justify-content: flex-start;
    padding-top: var(--bs-space-10);
  }

  .login-card {
    width: 100%;
    box-shadow: var(--bs-shadow-elevation2);
  }

  .captcha-img {
    width: 112px;
  }

  .login-footer {
    flex-direction: column;
    gap: var(--bs-space-1);
  }
}

/* ---- 减少动效偏好 ---- */
@media (prefers-reduced-motion: reduce) {
  .streamline,
  .gauge-arc {
    animation: none;
  }
}
</style>
