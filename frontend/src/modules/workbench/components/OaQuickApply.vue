<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { Promotion } from '@element-plus/icons-vue'
import WidgetShell from './WidgetShell.vue'
import { listOaCatalog } from '@/api/oa'
import type { OaForm } from '@/api/types'

defineOptions({ name: 'OaQuickApply' })

const { t } = useI18n()
const router = useRouter()

const forms = ref<OaForm[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const groups = await listOaCatalog()
    forms.value = (groups ?? []).flatMap((g) => g.forms ?? []).slice(0, 6)
  } catch {
    forms.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void load()
})

function apply(f: OaForm) {
  router.push({ path: '/oa/apply', query: { form: f.key } })
}
</script>

<template>
  <WidgetShell :title="t('workbench.widget.oaQuickApply')" :loading="loading">
    <template #actions>
      <el-button link type="primary" size="small" @click="router.push('/oa/apply')">
        {{ t('workbench.viewAll') }}
      </el-button>
    </template>

    <div v-if="!forms.length" class="empty">{{ t('workbench.emptyOaForms') }}</div>
    <div v-else class="form-grid">
      <button v-for="f in forms" :key="f.id" class="form-btn" @click="apply(f)">
        <el-icon class="form-icon"><Promotion /></el-icon>
        <span class="form-name">{{ f.name }}</span>
        <span v-if="f.description" class="form-desc" :title="f.description">{{ f.description }}</span>
      </button>
    </div>
  </WidgetShell>
</template>

<style scoped>
.empty {
  padding: var(--bs-space-5) 0;
  text-align: center;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-sm);
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
  gap: var(--bs-space-2);
}

.form-btn {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--bs-space-1);
  padding: var(--bs-space-2) var(--bs-space-3);
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-app);
  color: var(--bs-color-fg-default);
  cursor: pointer;
  text-align: left;
  transition:
    border-color var(--bs-duration) var(--bs-ease),
    box-shadow var(--bs-duration) var(--bs-ease);
}

.form-btn:hover {
  border-color: var(--bs-color-primary);
  box-shadow: var(--bs-shadow-elevation1);
}

.form-icon {
  color: var(--bs-color-primary);
}

.form-name {
  font-size: var(--bs-typography-font-size-sm);
  font-weight: 600;
}

.form-desc {
  width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: var(--bs-color-fg-muted);
  font-size: var(--bs-typography-font-size-xs);
}
</style>
