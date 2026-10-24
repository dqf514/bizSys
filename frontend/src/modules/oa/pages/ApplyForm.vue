<script setup lang="ts">
/** OA 新申请：模板目录（按分类分组卡片）→ 全屏弹窗动态表单发起，本地草稿自动保存。 */
import { computed, onBeforeUnmount, onMounted, ref, resolveComponent, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { ElIcon } from 'element-plus'
import ListPage from '@/components/list/ListPage.vue'
import FormRenderer from '@/modules/oa/components/FormRenderer.vue'
import { applyOa, listOaCatalog } from '@/api/oa'
import { useDict } from '@/composables/useDict'
import { useAuthStore } from '@/stores/auth'
import type { OaCatalogGroup, OaForm } from '@/api/types'

defineOptions({ name: 'ApplyForm' })

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const { options: dictOptions } = useDict()

const groups = ref<OaCatalogGroup[]>([])
const loading = ref(false)
const categoryLabels = ref<Record<string, string>>({})

async function load() {
  loading.value = true
  try {
    groups.value = await listOaCatalog()
    const opts = await dictOptions('oa_category')
    categoryLabels.value = Object.fromEntries(opts.map((o) => [o.value, o.label]))
  } catch {
    groups.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load().then(() => {
    // 工作台「OA 快捷发起」深链：?form=<key> 直接打开发起弹窗
    const key = String(route.query.form || '')
    if (!key) return
    const target = groups.value.flatMap((g) => g.forms ?? []).find((f) => f.key === key)
    if (target) openApply(target)
  })
})

function categoryLabel(c: string) {
  return categoryLabels.value[c] || t('oa.catalog.uncategorized')
}

function iconOf(name: string) {
  if (!name) return null
  const comp = resolveComponent(name)
  return comp ? (comp as never) : null
}

/* ---------- 发起弹窗 ---------- */
const dialogVisible = ref(false)
const currentForm = ref<OaForm | null>(null)
const formData = ref<Record<string, unknown>>({})
const rendererRef = ref<InstanceType<typeof FormRenderer> | null>(null)
const submitting = ref(false)

/* ---------- 本地草稿自动保存 ---------- */
const savedAt = ref('')
let saveTimer: ReturnType<typeof setTimeout> | null = null

const draftKey = computed(() =>
  currentForm.value ? `oa.draft.${auth.user?.id ?? 'anon'}.${currentForm.value.key}` : '',
)

// 默认值（checkbox/daterange 等数组型浅拷贝防串改）
function defaultData(form: OaForm): Record<string, unknown> {
  const data: Record<string, unknown> = {}
  for (const f of form.fields ?? []) {
    if (f.key && f.defaultValue !== undefined && f.defaultValue !== null && f.defaultValue !== '') {
      data[f.key] = Array.isArray(f.defaultValue) ? [...f.defaultValue] : f.defaultValue
    }
  }
  return data
}

function hhmmss(d: Date) {
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

function persistDraft() {
  if (!draftKey.value) return
  try {
    localStorage.setItem(draftKey.value, JSON.stringify({ data: formData.value, savedAt: Date.now() }))
    savedAt.value = hhmmss(new Date())
  } catch {
    /* storage 不可用（隐私模式等）时静默跳过 */
  }
}

watch(
  formData,
  () => {
    if (!dialogVisible.value || !currentForm.value) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(persistDraft, 1500)
  },
  { deep: true },
)

function clearDraft() {
  if (draftKey.value) localStorage.removeItem(draftKey.value)
  savedAt.value = ''
}

onBeforeUnmount(() => {
  if (saveTimer) clearTimeout(saveTimer)
})

function openApply(form: OaForm) {
  currentForm.value = form
  savedAt.value = ''
  const key = `oa.draft.${auth.user?.id ?? 'anon'}.${form.key}`
  let restored = false
  try {
    const raw = localStorage.getItem(key)
    if (raw) {
      const draft = JSON.parse(raw) as { data?: Record<string, unknown>; savedAt?: number }
      if (draft.data && Object.keys(draft.data).length) {
        formData.value = draft.data
        savedAt.value = draft.savedAt ? hhmmss(new Date(draft.savedAt)) : ''
        restored = true
      }
    }
  } catch {
    /* 草稿损坏时按新单处理 */
  }
  if (!restored) formData.value = defaultData(form)
  dialogVisible.value = true
  if (restored) ElMessage.info(t('oa.form.draftRestored'))
}

// 清空重填：二次确认后恢复默认值并删除本地草稿
async function resetForm() {
  try {
    await ElMessageBox.confirm(t('oa.form.clearConfirm'), {
      type: 'warning',
      confirmButtonText: t('common.action.confirm'),
      cancelButtonText: t('common.action.cancel'),
    })
  } catch {
    return
  }
  if (!currentForm.value) return
  clearDraft()
  formData.value = defaultData(currentForm.value)
}

async function submit() {
  const ok = await rendererRef.value?.validate()
  if (!ok) {
    ElMessage.warning(t('oa.form.fillRequired'))
    return
  }
  if (!currentForm.value) return
  submitting.value = true
  try {
    await applyOa(currentForm.value.id, formData.value)
    clearDraft()
    ElMessage.success(t('oa.form.submitSuccess'))
    dialogVisible.value = false
    router.push('/oa/my')
  } catch {
    /* http notifies */
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <ListPage :title="t('oa.catalog.title')" :loading="loading">
    <template #actions>
      <el-button @click="load()">{{ t('common.action.refresh') }}</el-button>
    </template>

    <div v-if="groups.length" class="catalog">
      <div v-for="g in groups" :key="g.category || '_'" class="catalog-group">
        <div class="group-title">{{ categoryLabel(g.category) }}</div>
        <div class="card-grid">
          <div v-for="f in g.forms" :key="f.id" class="form-card" @click="openApply(f)">
            <div class="card-icon">
              <el-icon :size="22"><component :is="iconOf(f.icon) || 'Document'" /></el-icon>
            </div>
            <div class="card-body">
              <div class="card-name">{{ f.name }}</div>
              <div class="card-desc">{{ f.description || '-' }}</div>
            </div>
            <el-button type="primary" plain size="small">{{ t('oa.catalog.apply') }}</el-button>
          </div>
        </div>
      </div>
    </div>
    <el-empty v-else-if="!loading" :description="t('oa.catalog.empty')" />
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="currentForm?.name" fullscreen append-to-body>
    <div class="apply-body">
      <div class="apply-meta">
        <span v-if="savedAt" class="saved-at">{{ t('oa.form.autoSaved', { time: savedAt }) }}</span>
      </div>
      <el-alert
        v-if="currentForm && !currentForm.flowDefinitionId"
        type="info"
        :title="t('oa.form.directPassTip')"
        :closable="false"
        class="direct-tip"
      />
      <FormRenderer
        v-if="dialogVisible && currentForm"
        ref="rendererRef"
        v-model="formData"
        :fields="currentForm.fields ?? []"
      />
    </div>
    <template #footer>
      <div class="dialog-footer">
        <el-button class="clear-btn" @click="resetForm">{{ t('oa.form.clearDraft') }}</el-button>
        <div>
          <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
          <el-button type="primary" :loading="submitting" @click="submit">{{ t('oa.form.submit') }}</el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.catalog {
  display: flex;
  flex-direction: column;
  gap: var(--bs-space-4);
  padding: var(--bs-space-3);
  overflow: auto;
}

.group-title {
  font-weight: 600;
  color: var(--bs-color-fg-default);
  margin-bottom: var(--bs-space-2);
}

.card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: var(--bs-space-3);
}

.form-card {
  display: flex;
  align-items: center;
  gap: var(--bs-space-3);
  padding: var(--bs-space-3);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.form-card:hover {
  border-color: var(--bs-color-primary);
  box-shadow: var(--bs-shadow-elevation2);
}

.card-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-fill-light);
  color: var(--bs-color-primary);
  flex-shrink: 0;
}

.card-body {
  flex: 1;
  min-width: 0;
}

.card-name {
  font-weight: 600;
  color: var(--bs-color-fg-default);
}

.card-desc {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.apply-body {
  max-width: 760px;
  margin: 0 auto;
  width: 100%;
}

.apply-meta {
  display: flex;
  justify-content: flex-end;
  min-height: 20px;
  margin-bottom: var(--bs-space-2);
}

.saved-at {
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}

.direct-tip {
  margin-bottom: var(--bs-space-3);
}

.dialog-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
