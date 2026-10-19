<script setup lang="ts">
/** OA 新申请：模板目录（按分类分组卡片）→ 弹窗动态表单发起。 */
import { onMounted, ref, resolveComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { ElIcon } from 'element-plus'
import ListPage from '@/components/list/ListPage.vue'
import FormRenderer from '@/modules/oa/components/FormRenderer.vue'
import { applyOa, listOaCatalog } from '@/api/oa'
import { useDict } from '@/composables/useDict'
import type { OaCatalogGroup, OaForm } from '@/api/types'

defineOptions({ name: 'ApplyForm' })

const { t } = useI18n()
const router = useRouter()
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

onMounted(() => void load())

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

function openApply(form: OaForm) {
  currentForm.value = form
  formData.value = {}
  dialogVisible.value = true
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

  <el-dialog v-model="dialogVisible" :title="currentForm?.name" width="640px" append-to-body>
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
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="submitting" @click="submit">{{ t('oa.form.submit') }}</el-button>
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

.direct-tip {
  margin-bottom: var(--bs-space-3);
}
</style>
