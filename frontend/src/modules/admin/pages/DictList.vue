<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { Search } from '@element-plus/icons-vue'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { clearDictCache } from '@/composables/useDict'
import {
  dictTypes,
  createDictType,
  createDictItem,
  updateDictItem,
  deleteDictItem,
  exportDicts,
} from '@/api/admin'
import type { DictItem, DictType } from '@/api/types'

defineOptions({ name: 'DictList' })

const { t } = useI18n()

const types = ref<DictType[]>([])
const loading = ref(false)
const activeType = ref<DictType | null>(null)

/** 本地全量：关键词同时过滤类型（code/name）与当前类型条目（label/labelEn/value） */
const keyword = ref('')
const filteredTypes = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return types.value
  return types.value.filter(
    (tp) =>
      tp.code?.toLowerCase().includes(kw) ||
      tp.name?.toLowerCase().includes(kw) ||
      (tp.items ?? []).some(
        (it) =>
          it.label?.toLowerCase().includes(kw) ||
          it.labelEn?.toLowerCase().includes(kw) ||
          String(it.value ?? '').toLowerCase().includes(kw),
      ),
  )
})
const filteredItems = computed(() => {
  const list = activeType.value?.items ?? []
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return list
  return list.filter(
    (it) =>
      it.label?.toLowerCase().includes(kw) ||
      it.labelEn?.toLowerCase().includes(kw) ||
      String(it.value ?? '').toLowerCase().includes(kw),
  )
})

async function load() {
  loading.value = true
  try {
    types.value = (await dictTypes()) ?? []
    if (!activeType.value && types.value.length) {
      activeType.value = types.value[0]!
    } else if (activeType.value) {
      activeType.value = types.value.find((x) => x.id === activeType.value!.id) ?? types.value[0] ?? null
    }
  } catch {
    types.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

const typeDialog = ref(false)
const typeFormRef = ref<FormInstance>()
const typeSaving = ref(false)
const typeForm = reactive({ code: '', name: '', remark: '' })

const itemDialog = ref(false)
const itemFormRef = ref<FormInstance>()
const itemSaving = ref(false)
const editingItemId = ref<number | null>(null)
const itemForm = reactive({
  dictTypeCode: '',
  label: '',
  labelEn: '',
  value: '',
  sort: 0,
  status: 'enabled',
  extra: '',
})

function openTypeCreate() {
  Object.assign(typeForm, { code: '', name: '', remark: '' })
  typeDialog.value = true
}

async function saveType() {
  if (!typeFormRef.value) return
  const ok = await typeFormRef.value.validate().catch(() => false)
  if (!ok) return
  typeSaving.value = true
  try {
    await createDictType({ ...typeForm })
    ElMessage.success(t('common.message.saveSuccess'))
    typeDialog.value = false
    void load()
  } catch {
    /* http notifies */
  } finally {
    typeSaving.value = false
  }
}

function openItemCreate() {
  if (!activeType.value) {
    ElMessage.warning(t('admin.dict.selectType'))
    return
  }
  editingItemId.value = null
  Object.assign(itemForm, {
    dictTypeCode: activeType.value.code,
    label: '',
    labelEn: '',
    value: '',
    sort: 0,
    status: 'enabled',
    extra: '',
  })
  itemDialog.value = true
}

function openItemEdit(row: DictItem) {
  editingItemId.value = row.id ?? null
  Object.assign(itemForm, {
    dictTypeCode: row.dictTypeCode ?? activeType.value?.code ?? '',
    label: row.label,
    labelEn: row.labelEn,
    value: row.value,
    sort: row.sort ?? 0,
    status: row.status ?? 'enabled',
    extra: row.extra ?? '',
  })
  itemDialog.value = true
}

async function saveItem() {
  if (!itemFormRef.value) return
  const ok = await itemFormRef.value.validate().catch(() => false)
  if (!ok) return
  itemSaving.value = true
  try {
    if (editingItemId.value) await updateDictItem(editingItemId.value, { ...itemForm })
    else await createDictItem({ ...itemForm, dictTypeCode: itemForm.dictTypeCode })
    clearDictCache(itemForm.dictTypeCode || undefined)
    ElMessage.success(t('common.message.saveSuccess'))
    itemDialog.value = false
    void load()
  } catch {
    /* http notifies */
  } finally {
    itemSaving.value = false
  }
}

async function removeItem(row: DictItem) {
  if (!row.id) return
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteDictItem(row.id)
    clearDictCache(row.dictTypeCode ?? activeType.value?.code ?? undefined)
    ElMessage.success(t('common.message.deleteSuccess'))
    void load()
  } catch {
    /* http notifies */
  }
}

const itemActions: ActionItem[] = [
  { key: 'edit', tip: 'common.action.edit', perm: 'admin:dict:edit' },
  { key: 'delete', tip: 'common.action.delete', perm: 'admin:dict:edit' },
]

function onItemAction(key: string, row: DictItem) {
  if (key === 'edit') openItemEdit(row)
  else if (key === 'delete') void removeItem(row)
}
</script>

<template>
  <ListPage :title="t('admin.dict.title')" :loading="loading">
    <template #actions>
      <el-input
        v-model="keyword"
        :placeholder="t('common.form.placeholderSearch')"
        :prefix-icon="Search"
        clearable
        class="local-filter"
      />
      <el-button v-permission="'admin:dict:edit'" type="primary" @click="openTypeCreate">
        {{ t('admin.dict.createType') }}
      </el-button>
      <el-button v-permission="'admin:dict:edit'" @click="openItemCreate">
        {{ t('admin.dict.createItem') }}
      </el-button>
      <ExportButton v-permission="'admin:dict:list'" :export-fn="() => exportDicts()" />
      <el-button @click="load()">{{ t('common.action.refresh') }}</el-button>
    </template>

    <div class="dict-layout">
      <div class="dict-types">
        <div
          v-for="tp in filteredTypes"
          :key="tp.id"
          class="dict-type-item"
          :class="{ active: activeType?.id === tp.id }"
          @click="activeType = tp"
        >
          <div class="type-code">{{ tp.code }}</div>
          <div class="type-name">{{ tp.name }}</div>
          <div class="type-count">{{ (tp.items || []).length }}</div>
        </div>
      </div>

      <div class="dict-items">
        <div class="items-header">
          <span class="items-title">
            {{ activeType ? `${activeType.code} · ${t('admin.dict.items')}` : t('admin.dict.selectType') }}
          </span>
        </div>
        <el-table :data="filteredItems" row-key="id" border stripe height="100%">
          <el-table-column :label="t('admin.dict.itemLabel')" prop="label" min-width="120" sortable />
          <el-table-column :label="t('admin.dict.itemLabelEn')" prop="labelEn" min-width="120" sortable />
          <el-table-column :label="t('admin.dict.itemValue')" prop="value" min-width="120" sortable />
          <el-table-column :label="t('admin.dict.itemSort')" prop="sort" width="80" sortable />
          <el-table-column :label="t('admin.dict.itemStatus')" prop="status" width="90" sortable>
            <template #default="{ row }">
              <StatusTag :status="String(row.status)" i18n-prefix="common.status" />
            </template>
          </el-table-column>
          <el-table-column :label="t('admin.dict.itemExtra')" prop="extra" min-width="100" />
          <el-table-column :label="t('common.action.operate')" width="90" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar :actions="itemActions" @select="(key: string) => onItemAction(key, row as DictItem)" />
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>
  </ListPage>

  <el-dialog v-model="typeDialog" :title="t('admin.dict.createType')" width="480px" append-to-body>
    <el-form ref="typeFormRef" :model="typeForm" label-width="100px">
      <el-form-item :label="t('admin.dict.typeCode')" prop="code" :rules="[{ required: true, message: t('common.form.required') }]">
        <el-input v-model="typeForm.code" />
      </el-form-item>
      <el-form-item :label="t('admin.dict.typeName')" prop="name" :rules="[{ required: true, message: t('common.form.required') }]">
        <el-input v-model="typeForm.name" />
      </el-form-item>
      <el-form-item :label="t('admin.dict.remark')">
        <el-input v-model="typeForm.remark" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="typeDialog = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="typeSaving" @click="saveType">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="itemDialog" :title="editingItemId ? t('admin.dict.editItem') : t('admin.dict.createItem')" width="520px" append-to-body>
    <el-form ref="itemFormRef" :model="itemForm" label-width="110px">
      <el-form-item :label="t('admin.dict.itemLabel')" prop="label" :rules="[{ required: true, message: t('common.form.required') }]">
        <el-input v-model="itemForm.label" />
      </el-form-item>
      <el-form-item :label="t('admin.dict.itemLabelEn')">
        <el-input v-model="itemForm.labelEn" />
      </el-form-item>
      <el-form-item :label="t('admin.dict.itemValue')" prop="value" :rules="[{ required: true, message: t('common.form.required') }]">
        <el-input v-model="itemForm.value" />
      </el-form-item>
      <el-form-item :label="t('admin.dict.itemSort')">
        <el-input-number v-model="itemForm.sort" :min="0" />
      </el-form-item>
      <el-form-item :label="t('admin.dict.itemStatus')">
        <el-radio-group v-model="itemForm.status">
          <el-radio value="enabled">{{ t('common.form.enabled') }}</el-radio>
          <el-radio value="disabled">{{ t('common.form.disabled') }}</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item :label="t('admin.dict.itemExtra')">
        <el-input v-model="itemForm.extra" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="itemDialog = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="itemSaving" @click="saveItem">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.dict-layout {
  display: grid;
  grid-template-columns: 240px 1fr;
  gap: var(--bs-space-3);
  flex: 1;
  min-height: 0;
}

.dict-types {
  overflow: auto;
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  padding: var(--bs-space-2);
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.dict-type-item {
  display: flex;
  align-items: center;
  gap: var(--bs-space-2);
  padding: 8px 10px;
  border-radius: var(--bs-radius-sm);
  cursor: pointer;
}

.dict-type-item:hover {
  background: var(--bs-color-fill-hover);
}

.dict-type-item.active {
  background: var(--bs-color-brand-primary-soft);
  color: var(--bs-color-primary);
}

.type-code {
  font-weight: 600;
  font-size: var(--bs-typography-font-size-sm);
}

.type-name {
  flex: 1;
  font-size: var(--bs-typography-font-size-xs);
  color: var(--bs-color-fg-muted);
}

.type-count {
  min-width: 18px;
  text-align: center;
  border-radius: var(--bs-radius-full);
  background: var(--bs-color-fill-light);
  font-size: 11px;
}

.dict-items {
  display: flex;
  flex-direction: column;
  min-height: 0;
  border: 1px solid var(--bs-color-border-subtle);
  border-radius: var(--bs-radius-md);
  background: var(--bs-color-bg-surface);
  overflow: hidden;
}

.items-header {
  padding: var(--bs-space-2) var(--bs-space-3);
  border-bottom: 1px solid var(--bs-color-border-subtle);
}

.items-title {
  font-weight: 600;
}

.local-filter {
  width: 220px;
}
</style>
