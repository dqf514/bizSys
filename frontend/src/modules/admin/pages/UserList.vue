<script setup lang="ts">
import { reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useListPage } from '@/composables/useListPage'
import {
  listUsers,
  createUser,
  updateUser,
  deleteUser,
  resetUserPassword,
  exportUsers,
  listRoles,
  listDepts,
} from '@/api/admin'
import type { AdminUser, Dept, Role } from '@/api/types'

defineOptions({ name: 'UserList' })

const { t } = useI18n()

const searchModel = ref<Record<string, any>>({ q: '' })
const searchFields: SearchField[] = [
  { key: 'q', labelKey: 'admin.user.username', width: 200 },
]

const statusTabs: StatusTabItem[] = [
  { value: 'all', labelKey: 'common.action.all' },
  { value: 'enabled', labelKey: 'common.form.enabled' },
  { value: 'disabled', labelKey: 'common.form.disabled' },
]

const list = useListPage<AdminUser>({
  fetch: async (params) => {
    const data = await listUsers({
      ...params,
      q: searchModel.value.q || undefined,
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) => exportUsers({ ...params, q: searchModel.value.q || undefined }),
})

const columns: ListColumn[] = [
  { prop: 'username', labelKey: 'admin.user.username', width: 140, fixed: 'left' },
  { prop: 'name', labelKey: 'admin.user.name', width: 120 },
  { prop: 'deptName', labelKey: 'admin.user.dept', minWidth: 140 },
  { prop: 'mobile', labelKey: 'admin.user.mobile', width: 120 },
  { prop: 'email', labelKey: 'admin.user.email', minWidth: 160 },
  { prop: 'status', labelKey: 'admin.user.status', width: 90 },
  { prop: 'roles', labelKey: 'admin.user.roles', width: 140 },
  { prop: 'createTime', labelKey: 'admin.user.createTime', width: 160 },
  { prop: 'lastLoginAt', labelKey: 'admin.user.lastLoginAt', width: 160 },
]

const dialogVisible = ref(false)
const dialogTitle = ref('')
const formRef = ref<FormInstance>()
const saving = ref(false)
const editingId = ref<number | null>(null)
const form = reactive({
  username: '',
  password: '',
  name: '',
  deptId: null as number | null,
  deptName: '',
  mobile: '',
  email: '',
  status: 'enabled',
  roleIds: [] as number[],
})

const roleOptions = ref<Role[]>([])
const deptTree = ref<Dept[]>([])

async function loadOptions() {
  try {
    const roles = await listRoles({ page: 1, size: 100 })
    roleOptions.value = roles.items ?? []
  } catch {
    roleOptions.value = []
  }
  try {
    const depts = await listDepts()
    deptTree.value = Array.isArray(depts) ? depts : (depts.items ?? [])
  } catch {
    deptTree.value = []
  }
}

function openCreate() {
  editingId.value = null
  dialogTitle.value = t('admin.user.create')
  Object.assign(form, {
    username: '',
    password: '',
    name: '',
    deptId: null,
    deptName: '',
    mobile: '',
    email: '',
    status: 'enabled',
    roleIds: [],
  })
  dialogVisible.value = true
  void loadOptions()
}

function openEdit(row: AdminUser) {
  editingId.value = row.id
  dialogTitle.value = t('admin.user.edit')
  Object.assign(form, {
    username: row.username,
    password: '',
    name: row.name,
    deptId: row.deptId,
    deptName: row.deptName ?? '',
    mobile: row.mobile ?? '',
    email: row.email ?? '',
    status: row.status,
    roleIds: (row as { roleIds?: number[] }).roleIds ?? [],
  })
  dialogVisible.value = true
  void loadOptions()
}

async function save() {
  if (!formRef.value) return
  const ok = await formRef.value.validate().catch(() => false)
  if (!ok) return
  saving.value = true
  try {
    const payload: Record<string, unknown> = {
      username: form.username,
      name: form.name,
      deptId: form.deptId,
      deptName: form.deptName,
      mobile: form.mobile,
      email: form.email,
      status: form.status,
      roleIds: form.roleIds,
    }
    if (editingId.value) {
      await updateUser(editingId.value, payload)
    } else {
      payload.password = form.password
      await createUser(payload as never)
    }
    ElMessage.success(t('common.message.saveSuccess'))
    dialogVisible.value = false
    list.refresh()
  } catch {
    /* http notifies */
  } finally {
    saving.value = false
  }
}

async function remove(row: AdminUser) {
  try {
    await ElMessageBox.confirm(t('common.message.deleteConfirm'), t('common.action.confirm'), {
      type: 'warning',
    })
  } catch {
    return
  }
  try {
    await deleteUser(row.id)
    ElMessage.success(t('common.message.deleteSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

async function resetPwd(row: AdminUser) {
  let password = ''
  try {
    const res = await ElMessageBox.prompt(t('admin.user.newPassword'), t('admin.user.resetPassword'), {
      inputType: 'password',
    })
    password = res.value
  } catch {
    return
  }
  if (!password) return
  try {
    await resetUserPassword(row.id, password)
    ElMessage.success(t('common.message.saveSuccess'))
  } catch {
    /* http notifies */
  }
}

async function toggleStatus(row: AdminUser) {
  const next = row.status === 'enabled' ? 'disabled' : 'enabled'
  const msg = next === 'enabled' ? t('admin.user.enableConfirm') : t('admin.user.disableConfirm')
  try {
    await ElMessageBox.confirm(msg, t('common.action.confirm'), { type: 'warning' })
  } catch {
    return
  }
  try {
    await updateUser(row.id, { status: next })
    ElMessage.success(t('common.message.saveSuccess'))
    list.refresh()
  } catch {
    /* http notifies */
  }
}

function onSearch() {
  list.search()
}

function onReset() {
  searchModel.value = { q: '' }
  list.reset()
}
</script>

<template>
  <ListPage :title="t('admin.user.title')" :loading="list.loading.value">
    <template #actions>
      <el-button v-permission="'admin:user:create'" type="primary" @click="openCreate">
        {{ t('admin.user.create') }}
      </el-button>
      <ExportButton v-permission="'admin:user:list:export'" :export-fn="() => list.exportList()" />
    </template>

    <template #searchBar>
      <SearchBar
        v-model="searchModel"
        :fields="searchFields"
        @search="onSearch"
        @reset="onReset"
      />
    </template>

    <template #statusTabs>
      <StatusTabs
        :tabs="statusTabs"
        :model-value="String(list.query.status)"
        @update:model-value="list.setStatus($event)"
      />
    </template>

    <template #table>
      <ListTable
        :columns="columns"
        :data="list.items.value as unknown as Record<string, unknown>[]"
        :loading="list.loading.value"
        :total="list.total.value"
        :page="Number(list.query.page)"
        :size="Number(list.query.size)"
        row-key="id"
        @update:page="list.setPage"
        @update:size="list.setSize"
      >
        <template #status="{ row }">
          <StatusTag :status="String(row.status)" i18n-prefix="common.status" />
        </template>
        <template #roles="{ row }">
          <el-tag v-for="r in (row.roles as string[])" :key="r" size="small" class="role-tag">{{ r }}</el-tag>
        </template>
        <template #username="{ row }">
          <el-button link type="primary" @click="openEdit(row as unknown as AdminUser)">{{ row.username }}</el-button>
        </template>
        <template #extraColumns>
          <el-table-column :label="t('common.action.operate')" width="240" fixed="right">
            <template #default="{ row }">
              <el-button v-permission="'admin:user:edit'" link type="primary" @click="openEdit(row as unknown as AdminUser)">
                {{ t('common.action.edit') }}
              </el-button>
              <el-button v-permission="'admin:user:edit'" link type="warning" @click="resetPwd(row as unknown as AdminUser)">
                {{ t('admin.user.resetPassword') }}
              </el-button>
              <el-button v-permission="'admin:user:edit'" link @click="toggleStatus(row as unknown as AdminUser)">
                {{ row.status === 'enabled' ? t('common.action.disable') : t('common.action.enable') }}
              </el-button>
              <el-button v-permission="'admin:user:delete'" link type="danger" @click="remove(row as unknown as AdminUser)">
                {{ t('common.action.delete') }}
              </el-button>
            </template>
          </el-table-column>
        </template>
      </ListTable>
    </template>
  </ListPage>

  <el-dialog v-model="dialogVisible" :title="dialogTitle" width="560px" append-to-body>
    <el-form ref="formRef" :model="form" label-width="110px">
      <el-form-item :label="t('admin.user.username')" prop="username" :rules="[{ required: true, message: t('common.form.required') }]">
        <el-input v-model="form.username" :placeholder="t('admin.user.usernamePlaceholder')" />
      </el-form-item>
      <el-form-item
        v-if="!editingId"
        :label="t('admin.user.password')"
        prop="password"
        :rules="[{ required: true, message: t('common.form.required') }]"
      >
        <el-input v-model="form.password" type="password" show-password :placeholder="t('admin.user.passwordPlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('admin.user.name')" prop="name" :rules="[{ required: true, message: t('common.form.required') }]">
        <el-input v-model="form.name" :placeholder="t('admin.user.namePlaceholder')" />
      </el-form-item>
      <el-form-item :label="t('admin.user.dept')">
        <el-tree-select
          v-model="form.deptId"
          :data="deptTree"
          :props="{ label: 'name', value: 'id', children: 'children' }"
          check-strictly
          clearable
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item :label="t('admin.user.mobile')">
        <el-input v-model="form.mobile" />
      </el-form-item>
      <el-form-item :label="t('admin.user.email')">
        <el-input v-model="form.email" />
      </el-form-item>
      <el-form-item :label="t('admin.user.status')">
        <el-radio-group v-model="form.status">
          <el-radio value="enabled">{{ t('common.form.enabled') }}</el-radio>
          <el-radio value="disabled">{{ t('common.form.disabled') }}</el-radio>
        </el-radio-group>
      </el-form-item>
      <el-form-item :label="t('admin.user.roles')">
        <el-select v-model="form.roleIds" multiple filterable style="width: 100%">
          <el-option v-for="r in roleOptions" :key="r.id" :label="r.name" :value="r.id" />
        </el-select>
      </el-form-item>
    </el-form>
    <template #footer>
      <el-button @click="dialogVisible = false">{{ t('common.action.cancel') }}</el-button>
      <el-button type="primary" :loading="saving" @click="save">{{ t('common.action.save') }}</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.role-tag {
  margin-right: 4px;
}
</style>
