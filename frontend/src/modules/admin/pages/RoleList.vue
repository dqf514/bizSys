<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import { useListPage } from '@/composables/useListPage'
import { listRoles, createRole, updateRole, deleteRole, grantRoleMenus, menuTree } from '@/api/admin'
import type { MenuNode, Role } from '@/api/types'

defineOptions({ name: 'RoleList' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [{ key: 'q', labelKey: 'admin.role.name', width: 200 }]

const list = useListPage<Role>({
  fetch: async (params) => {
    const data = await listRoles({ ...params, q: searchModel.value.q || undefined })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
})

const columns: ListColumn[] = [
  { prop: 'code', labelKey: 'admin.role.code', width: 140, sortable: 'code' },
  { prop: 'name', labelKey: 'admin.role.name', minWidth: 140, sortable: 'name' },
  { prop: 'dataScope', labelKey: 'admin.role.dataScope', width: 120 },
  { prop: 'status', labelKey: 'common.form.status', width: 100, sortable: 'status' },
  { prop: 'remark', labelKey: 'admin.role.remark', minWidth: 160 },
  { prop: 'createTime', labelKey: 'common.form.createTime', width: 160, sortable: 'create_time' },
]

const rowActions: ActionItem[] = [
  { key: 'grant', tip: 'admin.role.grantMenus', icon: 'Key', perm: 'admin:role:edit' },
  { key: 'edit', tip: 'common.action.edit', perm: 'admin:role:edit' },
  { key: 'delete', tip: 'common.action.delete', perm: 'admin:role:delete' },
]

function onRowAction(key: string, row: Role) {
  if (key === 'grant') void openGrant(row)
  else if (key === 'edit') openEdit(row)
  else if (key === 'delete') void remove(row)
}

const dialogVisible = ref(false)
const grantVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({ code: '', name: '', dataScope: 'all', status: 'enabled', remark: '' })

const menuTreeData = ref<MenuNode[]>([])
const checkedMenuIds = ref<number[]>([])
const grantRoleId = ref<number | null>(null)

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('admin.role.create')
  Object.assign(form, { code: '', name: '', dataScope: 'all', status: 'enabled', remark: '' })
  dialogVisible.value = true
}

function openEdit(row: Role) {
  editingId.value = row.id
  dialogTitle.value = t('admin.role.edit')
  Object.assign(form, {
    code: row.code,
    name: row.name,
    dataScope: row.dataScope,
    status: row.status,
    remark: row.remark ?? '',
  })
  dialogVisible.value = true
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    if (editingId.value) await updateRole(editingId.value, { ...form })
    else await createRole({ ...form })
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function remove(row: Role) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await deleteRole(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function openGrant(row: Role) {
  grantRoleId.value = row.id
  checkedMenuIds.value = [...(row.menuIds ?? [])]
  try {
    menuTreeData.value = await menuTree(true)
  } catch {
    menuTreeData.value = []
  }
  grantVisible.value = true
}

async function saveGrant() {
  if (!grantRoleId.value) return
  saving.value = true
  try {
    await grantRoleMenus(grantRoleId.value, checkedMenuIds.value)
    ElMessage.success(t('common.message.saveSuccess'))
    grantVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

function onTreeCheck(_data: unknown, info: { checkedKeys: number[]; checkedNodes?: unknown }) {
  checkedMenuIds.value = info.checkedKeys ?? []
}
</script>

<template>
  <ListPage :title="t('admin.role.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'admin:role:create'" type="primary" @click="openCreate">
        {{ t('admin.role.create') }}
      </el-button>
    </template>

    <template #searchBar>
      <SearchBar v-model="searchModel" :fields="searchFields" @search="list.search()" @reset="searchModel = {}; list.reset()" />
    </template>

    <template #table>
      <ListTable
        :columns="columns"
        :data="list.items.value as unknown as Record<string, unknown>[]"
        :loading="list.loading.value"
        :total="list.total.value"
        :page="Number(list.query.page)"
        :size="Number(list.query.size)"
        @update:page="list.setPage"
        @update:size="list.setSize"
        @sort-change="list.onSortChange"
      >
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="130" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar :actions="rowActions" @select="(k) => onRowAction(k, row as unknown as Role)" />
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="520px" append-to-body>
    <el-form ref="formRef" :model="form" label-width="110px">
      <el-form-item :label="t('admin.role.code')" prop="code" :rules="[{ required: true, message: t('common.form.required') }]">
        <el-input v-model="form.code" />
      </el-form-item>
      <el-form-item :label="t('admin.role.name')" prop="name" :rules="[{ required: true, message: t('common.form.required') }]">
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item :label="t('admin.role.dataScope')">
        <el-select v-model="form.dataScope" style="width: 100%">
          <el-option :label="t('admin.role.scopeAll')" value="all" />
          <el-option :label="t('admin.role.scopeDept')" value="dept" />
          <el-option :label="t('admin.role.scopeSelf')" value="self" />
        </el-select>
      </el-form-item>
      <el-form-item :label="t('common.form.status')">
        <el-radio-group v-model="form.status">
          <el-radio value="enabled">{{ t('common.form.enabled') }}</el-radio>
          <el-radio value="disabled">{{ t('common.form.disabled') }}</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item :label="t('admin.role.remark')">
        <el-input v-model="form.remark" type="textarea" :rows="2" />
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>

  <el-dialog v-model="grantVisible" :title="t('admin.role.menuTree')" width="480px" append-to-body>
    <el-tree
      :data="menuTreeData"
      node-key="id"
      show-checkbox
      default-expand-all
      :props="{ label: 'name', children: 'children' }"
      :default-checked-keys="checkedMenuIds"
      @check="onTreeCheck"
    />
    <template #footer>
      <el-button @click="grantVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="saveGrant">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>
</template>
