<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import { menuTree, createMenu, updateMenu, deleteMenu } from '@/api/admin'
import type { MenuNode } from '@/api/types'

defineOptions({ name: 'MenuList' })

const { t } = useI18n()

const treeData = ref<MenuNode[]>([])
const loading = ref(false)

async function load() {
  loading.value = true
  try {
    treeData.value = await menuTree(true)
  } catch {
    treeData.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => void load())

const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  parentId: null as number | null,
  name: '',
  titleKey: '',
  path: '',
  componentKey: '',
  icon: '',
  permission: '',
  menuType: 'menu' as 'dir' | 'menu' | 'button',
  sort: 0,
  visible: 1,
})

function openCreate(parent?: MenuNode) {
  editingId.value = null
  dialogTitle.value = t('admin.menu.create')
  Object.assign(form, {
    parentId: parent?.id ?? null,
    name: '',
    titleKey: '',
    path: '',
    componentKey: '',
    icon: '',
    permission: '',
    menuType: 'menu',
    sort: 0,
    visible: 1,
  })
  dialogVisible.value = true
}

function openEdit(row: MenuNode) {
  editingId.value = row.id
  dialogTitle.value = t('admin.menu.edit')
  Object.assign(form, {
    parentId: row.parentId,
    name: row.name,
    titleKey: row.titleKey,
    path: row.path,
    componentKey: row.componentKey,
    icon: row.icon,
    permission: row.permission,
    menuType: row.menuType,
    sort: row.sort,
    visible: row.visible,
  })
  dialogVisible.value = true
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    if (editingId.value) await updateMenu(editingId.value, { ...form })
    else await createMenu({ ...form })
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    void load()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function remove(row: MenuNode) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteMenu(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    void load()
  } catch {
    /* http notifies */
  }
}

function typeLabel(type: string) {
  if (type === 'dir') return t('admin.menu.typeDir')
  if (type === 'button') return t('admin.menu.typeButton')
  return t('admin.menu.typeMenu')
}
</script>

<template>
  <ListPage :title="t('admin.menu.title')" :loading="loading">
    <template #actions>
      <el-button v-permission="'admin:menu:create'" type="primary" @click="openCreate()">
        {{ t('admin.menu.create') }}
      </el-button>
      <el-button @click="load()">{{ t('common.action.refresh') }}</el-button>
    </template>

    <template #table>
      <el-table :data="treeData" row-key="id" border stripe default-expand-all height="100%">
        <el-table-column :label="t('admin.menu.name')" min-width="180">
          <template #default="{ row }">{{ row.name }}</template>
        </el-table-column>
        <el-table-column :label="t('admin.menu.titleKey')" prop="titleKey" min-width="140" />
        <el-table-column :label="t('admin.menu.path')" prop="path" min-width="140" />
        <el-table-column :label="t('admin.menu.componentKey')" prop="componentKey" min-width="160" />
        <el-table-column :label="t('admin.menu.permission')" prop="permission" min-width="140" />
        <el-table-column :label="t('admin.menu.menuType')" width="90">
          <template #default="{ row }">
            <el-tag size="small">{{ typeLabel(row.menuType) }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column :label="t('admin.menu.sort')" prop="sort" width="70" />
        <el-table-column :label="t('common.action.operate')" width="220" fixed="right">
          <template #default="{ row }">
            <el-button v-permission="'admin:menu:create'" link type="primary" @click="openCreate(row as MenuNode)">
              {{ t('common.action.create') }}
            </el-button>
            <el-button v-permission="'admin:menu:edit'" link type="primary" @click="openEdit(row as MenuNode)">
              {{ t('common.action.edit') }}
            </el-button>
            <el-button v-permission="'admin:menu:delete'" link type="danger" @click="remove(row as MenuNode)">
              {{ t('common.action.delete') }}
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="560px" append-to-body>
    <el-form ref="formRef" :model="form" label-width="120px">
      <el-form-item :label="t('admin.menu.menuType')">
        <el-radio-group v-model="form.menuType">
          <el-radio value="dir">{{ t('admin.menu.typeDir') }}</el-radio>
          <el-radio value="menu">{{ t('admin.menu.typeMenu') }}</el-radio>
          <el-radio value="button">{{ t('admin.menu.typeButton') }}</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item :label="t('admin.menu.name')" prop="name" :rules="[{ required: true, message: t('common.form.required') }]">
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item :label="t('admin.menu.titleKey')">
        <el-input v-model="form.titleKey" placeholder="menu.xxx" />
      </el-form-item>
      <el-form-item :label="t('admin.menu.path')">
        <el-input v-model="form.path" />
      </el-form-item>
      <el-form-item v-if="form.menuType === 'menu'" :label="t('admin.menu.componentKey')">
        <el-input v-model="form.componentKey" placeholder="crm/CustomerList" />
      </el-form-item>
      <el-form-item :label="t('admin.menu.icon')">
        <el-input v-model="form.icon" />
      </el-form-item>
      <el-form-item :label="t('admin.menu.permission')">
        <el-input v-model="form.permission" />
      </el-form-item>
      <el-form-item :label="t('admin.menu.sort')">
        <el-input-number v-model="form.sort" :min="0" />
      </el-form-item>
      <el-form-item :label="t('admin.menu.visible')">
        <el-switch v-model="form.visible" :active-value="1" :inactive-value="0" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>
</template>
