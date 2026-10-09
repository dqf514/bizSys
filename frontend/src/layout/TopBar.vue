<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessageBox, ElDropdown, ElDropdownMenu, ElDropdownItem, ElIcon, ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import {
  Fold,
  Expand,
  Search,
  Sunny,
  Moon,
  Monitor,
  User,
  SwitchButton,
  Lock,
  Odometer,
} from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import { useAuthStore } from '@/stores/auth'
import { useThemeStore, ACCENTS, type Density, type ThemeMode, type Accent } from '@/stores/theme'
import { changePassword as changePasswordApi } from '@/api/auth'
import type { Locale } from '@/i18n'

defineProps<{ collapsed: boolean }>()
const emit = defineEmits<{
  (e: 'toggle-nav'): void
  (e: 'open-command'): void
}>()

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const theme = useThemeStore()
const { t } = useI18n()
const profileVisible = ref(false)

const breadcrumbs = computed(() => {
  const matched = route.matched.filter((r) => r.meta?.titleKey || r.meta?.title)
  return matched.map((r) => ({
    path: r.path,
    title: r.meta?.titleKey ? t(String(r.meta.titleKey)) : String(r.meta?.title ?? ''),
  }))
})

function cycleTheme() {
  theme.toggleTheme()
}

function setThemeMode(mode: ThemeMode) {
  theme.setTheme(mode)
}

function setDensity(d: Density) {
  theme.setDensity(d)
}

function setAccent(a: Accent) {
  theme.setAccent(a)
}

function setLang(locale: Locale) {
  theme.setAppLocale(locale)
}

async function doLogout() {
  try {
    await ElMessageBox.confirm(t('auth.user.logoutConfirm'), t('common.action.confirm'), {
      type: 'warning',
    })
  } catch {
    return
  }
  await auth.doLogout()
  router.push('/login')
}

const pwdVisible = ref(false)
const pwdFormRef = ref<FormInstance>()
const pwdSaving = ref(false)
const pwdForm = reactive({ oldPassword: '', newPassword: '', confirmPassword: '' })

const pwdRules = computed<FormRules>(() => ({
  oldPassword: [{ required: true, message: t('common.form.required'), trigger: 'blur' }],
  newPassword: [{ required: true, message: t('common.form.required'), trigger: 'blur' }],
  confirmPassword: [
    { required: true, message: t('common.form.required'), trigger: 'blur' },
    {
      validator: (_rule, value: string, cb) =>
        value === pwdForm.newPassword ? cb() : cb(new Error(t('auth.user.passwordMismatch'))),
      trigger: 'blur',
    },
  ],
}))

function changePassword() {
  pwdForm.oldPassword = ''
  pwdForm.newPassword = ''
  pwdForm.confirmPassword = ''
  pwdVisible.value = true
}

async function submitPassword() {
  if (!pwdFormRef.value) return
  const ok = await pwdFormRef.value.validate().catch(() => false)
  if (!ok) return
  pwdSaving.value = true
  try {
    await changePasswordApi(pwdForm.oldPassword, pwdForm.newPassword)
    pwdVisible.value = false
    ElMessage.success(t('auth.user.changeSuccess'))
    try {
      await ElMessageBox.confirm(t('auth.user.reloginTip'), t('common.action.confirm'), {
        confirmButtonText: t('auth.user.relogin'),
        cancelButtonText: t('auth.user.reloginLater'),
        type: 'success',
      })
      await auth.doLogout()
      router.push('/login')
    } catch {
      /* stay logged in */
    }
  } catch {
    /* http notifies */
  } finally {
    pwdSaving.value = false
  }
}
</script>

<template>
  <div class="topbar">
    <button class="icon-btn" type="button" :title="t('common.action.collapse')" @click="emit('toggle-nav')">
      <ElIcon :size="16">
        <Fold v-if="!collapsed" />
        <Expand v-else />
      </ElIcon>
    </button>

    <div class="brand">
      <ElIcon :size="18" class="brand-icon"><Odometer /></ElIcon>
      <span class="brand-text">{{ t('common.app.short') }}</span>
    </div>

    <el-breadcrumb separator="/" class="crumb">
      <el-breadcrumb-item v-for="(item, i) in breadcrumbs" :key="i" :to="i < breadcrumbs.length - 1 ? { path: item.path } : undefined">
        {{ item.title }}
      </el-breadcrumb-item>
    </el-breadcrumb>

    <div class="spacer" />

    <button class="cmd-trigger" type="button" @click="emit('open-command')">
      <ElIcon :size="14"><Search /></ElIcon>
      <span>{{ t('common.command.placeholder') }}</span>
      <kbd>Ctrl K</kbd>
    </button>

    <div class="actions">
      <ElDropdown trigger="click" @command="setDensity">
        <button class="icon-btn" type="button" :title="t('common.theme.density')">
          <ElIcon :size="16"><Monitor /></ElIcon>
        </button>
        <template #dropdown>
          <ElDropdownMenu>
            <ElDropdownItem command="comfortable" :disabled="theme.density === 'comfortable'">
              {{ t('common.theme.comfortable') }}
            </ElDropdownItem>
            <ElDropdownItem command="compact" :disabled="theme.density === 'compact'">
              {{ t('common.theme.compact') }}
            </ElDropdownItem>
          </ElDropdownMenu>
        </template>
      </ElDropdown>

      <ElDropdown trigger="click" @command="setThemeMode">
        <button class="icon-btn" type="button" :title="t('common.theme.toggleTheme')" @click="cycleTheme">
          <ElIcon :size="16">
            <Moon v-if="theme.theme === 'light'" />
            <Sunny v-else />
          </ElIcon>
        </button>
        <template #dropdown>
          <ElDropdownMenu>
            <ElDropdownItem command="light">{{ t('common.theme.light') }}</ElDropdownItem>
            <ElDropdownItem command="dark">{{ t('common.theme.dark') }}</ElDropdownItem>
            <ElDropdownItem command="brand-smvic">{{ t('common.theme.brand') }}</ElDropdownItem>
          </ElDropdownMenu>
        </template>
      </ElDropdown>

      <ElDropdown trigger="click" @command="setAccent">
        <button class="icon-btn accent-btn" type="button" :title="t('common.theme.accent')">
          <span class="accent-dot" />
        </button>
        <template #dropdown>
          <ElDropdownMenu>
            <ElDropdownItem v-for="a in ACCENTS" :key="a" :command="a" :disabled="theme.accent === a">
              <span class="accent-swatch" :class="`accent-${a}`" /> {{ a }}
            </ElDropdownItem>
          </ElDropdownMenu>
        </template>
      </ElDropdown>

      <ElDropdown trigger="click" @command="setLang">
        <button class="icon-btn lang-btn" type="button" :title="t('common.lang.switch')">
          {{ theme.locale === 'zh-CN' ? t('common.lang.shortZh') : t('common.lang.shortEn') }}
        </button>
        <template #dropdown>
          <ElDropdownMenu>
            <ElDropdownItem command="zh-CN" :disabled="theme.locale === 'zh-CN'">
              {{ t('common.lang.zhCN') }}
            </ElDropdownItem>
            <ElDropdownItem command="en-US" :disabled="theme.locale === 'en-US'">
              {{ t('common.lang.enUS') }}
            </ElDropdownItem>
          </ElDropdownMenu>
        </template>
      </ElDropdown>

      <ElDropdown trigger="click">
        <button class="account-btn" type="button">
          <span class="avatar">{{ (auth.user?.name || auth.user?.username || '?').slice(0, 1) }}</span>
          <span class="account-name">{{ auth.user?.name || auth.user?.username }}</span>
        </button>
        <template #dropdown>
          <ElDropdownMenu>
            <ElDropdownItem @click="profileVisible = true">
              <ElIcon><User /></ElIcon>{{ t('auth.user.profile') }}
            </ElDropdownItem>
            <ElDropdownItem @click="changePassword">
              <ElIcon><Lock /></ElIcon>{{ t('auth.user.changePassword') }}
            </ElDropdownItem>
            <ElDropdownItem divided @click="doLogout">
              <ElIcon><SwitchButton /></ElIcon>{{ t('auth.user.logout') }}
            </ElDropdownItem>
          </ElDropdownMenu>
        </template>
      </ElDropdown>
    </div>

    <el-dialog v-model="profileVisible" :title="t('auth.user.profile')" width="420px" append-to-body>
      <el-descriptions :column="1" border>
        <el-descriptions-item :label="t('auth.login.username')">{{ auth.user?.username }}</el-descriptions-item>
        <el-descriptions-item :label="t('auth.user.profile')">{{ auth.user?.name }}</el-descriptions-item>
        <el-descriptions-item :label="t('auth.user.dept')">{{ auth.user?.deptName || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="t('auth.user.roles')">{{ (auth.user?.roles || []).join(', ') }}</el-descriptions-item>
        <el-descriptions-item :label="t('auth.user.email')">{{ auth.user?.email || '-' }}</el-descriptions-item>
        <el-descriptions-item :label="t('auth.user.mobile')">{{ auth.user?.mobile || '-' }}</el-descriptions-item>
      </el-descriptions>
    </el-dialog>

    <el-dialog v-model="pwdVisible" :title="t('auth.user.changePassword')" width="420px" append-to-body>
      <el-form ref="pwdFormRef" :model="pwdForm" :rules="pwdRules" label-width="110px">
        <el-form-item :label="t('auth.user.oldPassword')" prop="oldPassword">
          <el-input v-model="pwdForm.oldPassword" type="password" show-password />
        </el-form-item>
        <el-form-item :label="t('auth.user.newPassword')" prop="newPassword">
          <el-input v-model="pwdForm.newPassword" type="password" show-password />
        </el-form-item>
        <el-form-item :label="t('auth.user.confirmPassword')" prop="confirmPassword">
          <el-input v-model="pwdForm.confirmPassword" type="password" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="pwdVisible = false">{{ t('common.action.cancel') }}</el-button>
        <el-button type="primary" :loading="pwdSaving" @click="submitPassword">
          {{ t('common.action.save') }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.topbar {
  height: 100%;
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  padding: 0 var(--bs-space-3);
}

.icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: none;
  border-radius: var(--bs-radius-sm);
  background: transparent;
  color: var(--bs-color-fg-secondary);
  cursor: pointer;
}

.icon-btn:hover {
  background: var(--bs-color-fill-hover);
  color: var(--bs-color-fg-default);
}

.brand {
  display: flex;
  align-items: center;
  gap: var(--bs-space-1);
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.brand-icon {
  color: var(--bs-color-primary);
}

.crumb {
  margin-left: var(--bs-space-2);
}

.spacer {
  flex: 1;
}

.cmd-trigger {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  height: 28px;
  min-width: 220px;
  padding: 0 var(--bs-space-2);
  border: 1px solid var(--bs-color-border-default);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-fill-lighter);
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
  cursor: pointer;
}

.cmd-trigger kbd {
  margin-left: auto;
  padding: 0 4px;
  border: 1px solid var(--bs-color-border-default);
  border-radius: var(--bs-radius-sm);
  background: var(--bs-color-bg-surface);
  font-size: 10px;
}

.actions {
  display: flex;
  align-items: center;
  gap: var(--bs-space-1);
}

.lang-btn {
  width: auto;
  padding: 0 var(--bs-space-2);
  font-size: var(--bs-typography-font-size-xs);
  font-weight: 600;
}

.accent-dot {
  width: 12px;
  height: 12px;
  border-radius: var(--bs-radius-full);
  background: var(--bs-color-primary);
}

.accent-swatch {
  display: inline-block;
  width: 10px;
  height: 10px;
  margin-right: 6px;
  border-radius: var(--bs-radius-full);
  vertical-align: middle;
}

.accent-blue { background: var(--bs-color-accent-blue); }
.accent-green { background: var(--bs-color-accent-green); }
.accent-purple { background: var(--bs-color-accent-purple); }
.accent-orange { background: var(--bs-color-accent-orange); }
.accent-cyan { background: var(--bs-color-accent-cyan); }
.accent-red { background: var(--bs-color-accent-red); }

.account-btn {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  height: 32px;
  padding: 0 var(--bs-space-2);
  border: none;
  border-radius: var(--bs-radius-md);
  background: transparent;
  color: var(--bs-color-fg-default);
  cursor: pointer;
}

.account-btn:hover {
  background: var(--bs-color-fill-hover);
}

.avatar {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: var(--bs-radius-full);
  background: var(--bs-color-brand-primary-soft);
  color: var(--bs-color-primary);
  font-size: var(--bs-typography-font-size-xs);
  font-weight: 600;
}

.account-name {
  font-size: var(--bs-typography-font-size-sm);
}
</style>
