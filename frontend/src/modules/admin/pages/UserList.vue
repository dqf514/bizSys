<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { useI18n } from 'vue-i18n'
import ListPage from '@/components/list/ListPage.vue'
import SearchBar, { type SearchField } from '@/components/list/SearchBar.vue'
import StatusTabs, { type StatusTabItem } from '@/components/list/StatusTabs.vue'
import ListTable, { type ListColumn } from '@/components/list/ListTable.vue'
import ActionBar, { type ActionItem } from '@/components/list/ActionBar.vue'
import ExportButton from '@/components/list/ExportButton.vue'
import StatusTag from '@/components/common/StatusTag.vue'
import { useListPage } from '@/composables/useListPage'
import {
  listUsers,
  userCounts,
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

const statusTabs = ref<StatusTabItem[]>([
  { value: 'all', labelKey: 'common.action.all', count: 0 },
  { value: 'enabled', labelKey: 'common.form.enabled', count: 0 },
  { value: 'disabled', labelKey: 'common.form.disabled', count: 0 },
])

const counts = ref<Record<string, number>>({})

async function loadCounts() {
  try {
    counts.value = (await userCounts()) ?? {}
    let all = 0
    for (const tab of statusTabs.value) {
      if (tab.value === 'all') continue
      tab.count = counts.value[tab.value] ?? 0
      all += tab.count
    }
    const allTab = statusTabs.value.find((x) => x.value === 'all')
    if (allTab) allTab.count = all
  } catch {
    /* counts optional */
  }
}

onMounted(() => void loadCounts())

const list = useListPage<AdminUser>({
  fetch: async (params) => {
    const data = await listUsers({
      ...params,
      q: searchModel.value.q || undefined,
    })
    return { items: data.items ?? [], total: data.total ?? 0 }
  },
  exportFn: (params) => exportUsers({ ...params, q: searchModel.value.q || undefined }),
  onLoaded: () => {
    void loadCounts()
  },
})

const columns: ListColumn[] = [
  { prop: 'username', labelKey: 'admin.user.username', width: 140, fixed: 'left', sortable: 'username' },
  { prop: 'name', labelKey: 'admin.user.name', width: 120, sortable: 'name' },
  { prop: 'deptName', labelKey: 'admin.user.dept', minWidth: 140 },
  { prop: 'mobile', labelKey: 'admin.user.mobile', width: 120 },
  { prop: 'email', labelKey: 'admin.user.email', minWidth: 160 },
  { prop: 'status', labelKey: 'admin.user.status', width: 90, sortable: 'status' },
  { prop: 'roles', labelKey: 'admin.user.roles', width: 140 },
  { prop: 'createTime', labelKey: 'admin.user.createTime', width: 160, sortable: 'create_time' },
  { prop: 'lastLoginAt', labelKey: 'admin.user.lastLoginAt', width: 160, sortable: 'last_login_at' },
]

/** 启停动作图标/文案随当前状态切换 */
function rowActions(row: AdminUser): ActionItem[] {
  const enabled = row.status === 'enabled'
  return [
    { key: 'edit', tip: 'common.action.edit', perm: 'admin:user:edit' },
    { key: 'resetPwd', tip: 'admin.user.resetPassword', icon: 'Key', perm: 'admin:user:edit' },
    {
      key: enabled ? 'disable' : 'enable',
      tip: enabled ? 'common.action.disable' : 'common.action.enable',
      perm: 'admin:user:edit',
    },
    { key: 'delete', tip: 'common.action.delete', perm: 'admin:user:delete' },
  ]
}

function onRowAction(key: string, row: AdminUser) {
  if (key === 'edit') openEdit(row)
  else if (key === 'resetPwd') void resetPwd(row)
  else if (key === 'enable' || key === 'disable') void toggleStatus(row)
  else if (key === 'delete') void remove(row)
}

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
  employeeNo: '',
  hireDate: '',
  jobLevel: '',
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
    employeeNo: '',
    hireDate: '',
    jobLevel: '',
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
    employeeNo: row.employeeNo ?? '',
    hireDate: row.hireDate ?? '',
    jobLevel: row.jobLevel ?? '',
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
      employeeNo: form.employeeNo,
      hireDate: form.hireDate || null,
      jobLevel: form.jobLevel,
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
        @sort-change="list.onSortChange"
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
          <el-table-column :label="t('common.action.operate')" width="130" fixed="right" align="center" header-align="center">
            <template #default="{ row }">
              <ActionBar :actions="rowActions(row as unknown as AdminUser)" @select="(k) => onRowAction(k, row as unknown as AdminUser)" />
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
      <el-form-item :label="t('admin.user.employeeNo')">
        <el-input v-model="form.employeeNo" maxlength="32" />
      </el-form-item>
      <el-form-item :label="t('admin.user.hireDate')">
        <el-date-picker
          v-model="form.hireDate"
          type="date"
          value-format="YYYY-MM-DD"
          style="width: 100%"
        />
      </el-form-item>
      <el-form-item :label="t('admin.user.jobLevel')">
        <el-input v-model="form.jobLevel" maxlength="32" />
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
