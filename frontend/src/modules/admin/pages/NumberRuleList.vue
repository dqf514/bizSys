<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import {
  listNumberRules,
  createNumberRule,
  updateNumberRule,
  previewNumberRule,
  resetNumberRule,
} from '@/api/admin'
import { useDict } from '@/composables/useDict'
import type { NumberRule } from '@/api/types'

defineOptions({ name: 'NumberRuleList' })

const { t } = useI18n()
const { options: dictOptions } = useDict()

const items = ref<NumberRule[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    const data = await listNumberRules()
    items.value = Array.isArray(data) ? data : (data.items ?? [])
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

/* ---------- 业务类型 / 分类映射 ---------- */
// biz_type → 分类字典类型（分类键取该字典的 value）
const BIZ_CATEGORY_DICT: Record<string, string> = {
  contract: 'contract_type',
  task: 'task_type',
}
const BIZ_TYPES = ['customer', 'contract', 'task', 'report', 'settlement', 'payment']

function bizLabel(b: string) {
  const key = `admin.numbering.biz${b.charAt(0).toUpperCase()}${b.slice(1)}`
  const v = t(key)
  return v === key ? b : v
}

/* ---------- 字典分类选项（编辑器内按 bizType 动态加载） ---------- */
const categoryOpts = ref<{ label: string; value: string }[]>([])
const categoryLabels = ref<Record<string, string>>({})

async function loadCategoryLabels() {
  const map: Record<string, string> = {}
  for (const dt of Object.values(BIZ_CATEGORY_DICT)) {
    for (const o of await dictOptions(dt)) map[o.value] = o.label
  }
  categoryLabels.value = map
}

onMounted(() => void loadCategoryLabels())

function categoryLabel(row: NumberRule) {
  if (!row.categoryKey) return t('admin.numbering.categoryFallback')
  return categoryLabels.value[row.categoryKey] || row.categoryKey
}

/* ---------- 编辑器 ---------- */
const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  bizType: 'customer',
  categoryKey: '',
  prefix: '',
  yearDigits: 4,
  monthDigits: 2,
  dayDigits: 2,
  seqLen: 4,
  seqStart: 1,
  separator: '',
  resetCycle: 'none',
  enabled: 1 as number,
})

watch(
  () => form.bizType,
  async (bt) => {
    const dictType = BIZ_CATEGORY_DICT[bt]
    categoryOpts.value = dictType ? await dictOptions(dictType) : []
    if (!dictType) form.categoryKey = ''
  },
)

function cycleLabel(c: string) {
  if (c === 'daily') return t('admin.numbering.cycleDaily')
  if (c === 'monthly') return t('admin.numbering.cycleMonthly')
  if (c === 'yearly') return t('admin.numbering.cycleYearly')
  return t('admin.numbering.cycleNone')
}

function datePartLabel(row: NumberRule) {
  const parts: string[] = []
  if (row.yearDigits) parts.push(row.yearDigits === 4 ? 'YYYY' : 'YY')
  if (row.monthDigits) parts.push('MM')
  if (row.dayDigits) parts.push('DD')
  return parts.length ? parts.join(row.separator || '') : '-'
}

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('admin.numbering.create')
  Object.assign(form, {
    bizType: 'customer',
    categoryKey: '',
    prefix: '',
    yearDigits: 4,
    monthDigits: 2,
    dayDigits: 2,
    seqLen: 4,
    seqStart: 1,
    separator: '',
    resetCycle: 'none',
    enabled: 1,
  })
  dialogVisible.value = true
}

function openEdit(row: NumberRule) {
  editingId.value = row.id
  dialogTitle.value = t('admin.numbering.edit')
  Object.assign(form, {
    bizType: row.bizType,
    categoryKey: row.categoryKey ?? '',
    prefix: row.prefix,
    yearDigits: Number(row.yearDigits) || 0,
    monthDigits: Number(row.monthDigits) || 0,
    dayDigits: Number(row.dayDigits) || 0,
    seqLen: row.seqLen,
    seqStart: Number(row.seqStart ?? 1),
    separator: row.separator ?? '',
    resetCycle: row.resetCycle,
    enabled: Number(row.enabled),
  })
  dialogVisible.value = true
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    if (editingId.value) await updateNumberRule(editingId.value, { ...form })
    else await createNumberRule({ ...form })
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    void load()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

/* ---------- 实时预览（调后端 preview，不占号） ---------- */
const livePreview = ref('')
let previewTimer: ReturnType<typeof setTimeout> | null = null

watch(
  () => ({ ...form }),
  () => {
    if (!dialogVisible.value) return
    if (previewTimer) clearTimeout(previewTimer)
    previewTimer = setTimeout(async () => {
      try {
        const r = await previewNumberRule({ ...form })
        livePreview.value = r.preview
      } catch {
        /* 输入非法时保持上一次预览 */
      }
    }, 300)
  },
  { deep: true },
)

watch(dialogVisible, async (v) => {
  if (v) {
    try {
      livePreview.value = (await previewNumberRule({ ...form })).preview
    } catch {
      livePreview.value = ''
    }
  }
})

/* ---------- 重置序列 ---------- */
async function doReset(row: NumberRule) {
  let value = 0
  try {
    const r = await ElMessageBox.prompt(t('admin.numbering.resetSeqPrompt'), t('admin.numbering.resetSeq'), {
      confirmButtonText: t('common.action.confirm'),
      cancelButtonText: t('common.action.cancel'),
      inputValue: '0',
      inputPattern: /^\d+$/,
      inputErrorMessage: t('admin.numbering.resetSeqInvalid'),
    })
    value = Number(r.value)
  } catch {
    return
  }
  try {
    const r = await resetNumberRule(row.id, value)
    ElMessage.success(t('admin.numbering.resetSeqDone', { period: r.period, value: r.value }))
    void load()
  } catch {
    /* http notifies */
  }
}

const hasCategory = computed(() => Boolean(BIZ_CATEGORY_DICT[form.bizType]))

const EDIT_PERM = 'admin:numbering:edit'

const ruleActions: ActionItem[] = [
  { key: 'edit', tip: 'common.action.edit', perm: EDIT_PERM },
  { key: 'resetSeq', tip: 'admin.numbering.resetSeq', icon: 'RefreshLeft', perm: EDIT_PERM },
]

function onAction(key: string, row: NumberRule) {
  if (key === 'edit') openEdit(row)
  else if (key === 'resetSeq') void doReset(row)
}
</script>

<template>
  <ListPage :title="t('admin.numbering.title')" :loading="loading">
    <template #actions>
      <el-button v-permission="'admin:numbering:edit'" type="primary" @click="openCreate">
        {{ t('admin.numbering.create') }}
      </el-button>
      <el-button @click="load()">{{ t('common.action.refresh') }}</el-button>
    </template>

    <template #table>
      <el-table :data="items" row-key="id" border stripe height="100%">
        <el-table-column :label="t('admin.numbering.bizType')" prop="bizType" min-width="100" sortable>
          <template #default="{ row }">{{ bizLabel(row.bizType) }}</template>
        </el-table-column>
        <el-table-column :label="t('admin.numbering.categoryKey')" prop="categoryKey" min-width="120" sortable>
          <template #default="{ row }">{{ categoryLabel(row) }}</template>
        </el-table-column>
        <el-table-column :label="t('admin.numbering.prefix')" prop="prefix" width="90" sortable />
        <el-table-column :label="t('admin.numbering.datePart')" min-width="110">
          <template #default="{ row }">{{ datePartLabel(row) }}</template>
        </el-table-column>
        <el-table-column :label="t('admin.numbering.seqLen')" prop="seqLen" width="120" sortable>
          <template #default="{ row }">
            {{ row.seqLen }} / {{ t('admin.numbering.seqStartShort') }}{{ row.seqStart ?? 1 }}
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.numbering.separator')" width="80">
          <template #default="{ row }">{{ row.separator || '-' }}</template>
        </el-table-column>
        <el-table-column :label="t('admin.numbering.resetCycle')" prop="resetCycle" width="100" sortable>
          <template #default="{ row }">{{ cycleLabel(row.resetCycle) }}</template>
        </el-table-column>
        <el-table-column :label="t('admin.numbering.enabled')" prop="enabled" width="80" sortable>
          <template #default="{ row }">
            <el-tag :type="Number(row.enabled) ? 'success' : 'info'" size="small">
              {{ Number(row.enabled) ? t('common.form.enabled') : t('common.form.disabled') }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.numbering.preview')" min-width="160">
          <template #default="{ row }">
            <code class="preview-code">{{ row.preview || row.example || '-' }}</code>
          </template>
        </el-table-column>
        <el-table-column :label="t('common.action.operate')" width="90" fixed="right" align="center" header-align="center">
          <template #default="{ row }">
            <ActionBar :actions="ruleActions" @select="(key: string) => onAction(key, row as NumberRule)" />
          </template>
        </el-table-column>
      </el-table>
    </template>
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="640px" append-to-body>
    <el-form ref="formRef" :model="form" label-width="130px">
      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item :label="t('admin.numbering.bizType')" prop="bizType" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-select v-model="form.bizType" style="width: 100%" :disabled="!!editingId">
              <el-option v-for="b in BIZ_TYPES" :key="b" :label="bizLabel(b)" :value="b" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('admin.numbering.categoryKey')">
            <el-select
              v-model="form.categoryKey"
              style="width: 100%"
              clearable
              :disabled="!hasCategory"
              :placeholder="hasCategory ? t('admin.numbering.categoryPlaceholder') : t('admin.numbering.categoryNa')"
            >
              <el-option v-for="o in categoryOpts" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
            <div class="form-tip">{{ t('admin.numbering.categoryTip') }}</div>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('admin.numbering.prefix')" prop="prefix" :rules="[{ required: true, message: t('common.form.required') }]">
            <el-input v-model="form.prefix" maxlength="16" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('admin.numbering.separator')">
            <el-input v-model="form.separator" maxlength="4" :placeholder="t('admin.numbering.separatorTip')" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('admin.numbering.yearDigits')" label-width="100px">
            <el-select v-model="form.yearDigits" style="width: 100%">
              <el-option :label="t('admin.numbering.digit4')" :value="4" />
              <el-option :label="t('admin.numbering.digit2')" :value="2" />
              <el-option :label="t('admin.numbering.digitNone')" :value="0" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('admin.numbering.monthDigits')" label-width="100px">
            <el-select v-model="form.monthDigits" style="width: 100%">
              <el-option :label="t('admin.numbering.digit2')" :value="2" />
              <el-option :label="t('admin.numbering.digitNone')" :value="0" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('admin.numbering.dayDigits')" label-width="100px">
            <el-select v-model="form.dayDigits" style="width: 100%">
              <el-option :label="t('admin.numbering.digit2')" :value="2" />
              <el-option :label="t('admin.numbering.digitNone')" :value="0" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('admin.numbering.seqLen')" label-width="100px">
            <el-input-number v-model="form.seqLen" :min="1" :max="10" style="width: 100%" controls-position="right" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('admin.numbering.seqStart')" label-width="100px">
            <el-input-number v-model="form.seqStart" :min="0" style="width: 100%" controls-position="right" />
          </el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="t('admin.numbering.resetCycle')" label-width="100px">
            <el-select v-model="form.resetCycle" style="width: 100%">
              <el-option :label="t('admin.numbering.cycleNone')" value="none" />
              <el-option :label="t('admin.numbering.cycleDaily')" value="daily" />
              <el-option :label="t('admin.numbering.cycleMonthly')" value="monthly" />
              <el-option :label="t('admin.numbering.cycleYearly')" value="yearly" />
            </el-select>
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="t('admin.numbering.enabled')">
            <el-switch v-model="form.enabled" :active-value="1" :inactive-value="0" />
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <el-form-item :label="t('admin.numbering.previewTitle')">
            <code class="preview-code preview-live">{{ livePreview || '-' }}</code>
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.preview-code {
  padding: 2px 6px;
  border-radius: var(--bs-radius-sm);
  background: var(--bs-color-fill-lighter);
  font-family: var(--bs-typography-font-family-mono);
  font-size: var(--bs-typography-font-size-xs);
}

.preview-live {
  font-size: var(--bs-typography-font-size-md);
}

.form-tip {
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
  line-height: 1.4;
}
</style>
