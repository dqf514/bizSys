/**
 * 资产与库存域共用的下拉选项加载器。
 *
 * 统一框架：部门 → `sys_dept`（listDepts），供应公司 → `crm_customer`（partner_type=supplier/both），
 * 仓库/库位/存货/样件/工具 → `asset` 域自己的主数据接口。
 */
import { ref } from 'vue'
import { listDepts } from '@/api/admin'
import { customerOptions } from '@/api/crm'
import {
  listAllItems,
  listAllLocations,
  listAllPrototypes,
  listAllTools,
  listAssets,
  listWarehouses,
} from '@/api/asset'
import type {
  AssetItemOption,
  AssetLocationOption,
  AssetPrototypeOption,
  AssetToolOption,
  Dept,
} from '@/api/types'

export interface AssetOption {
  value: number
  label: string
}

/** 部门树（sys_dept） */
export function useDeptTree() {
  const deptTree = ref<Dept[]>([])

  async function load() {
    try {
      const data = await listDepts()
      deptTree.value = Array.isArray(data) ? data : (data.items ?? [])
    } catch {
      deptTree.value = []
    }
  }

  void load()
  return { deptTree, load }
}

/** 仓库下拉（ast_warehouse） */
export function useWarehouseOptions() {
  const opts = ref<AssetOption[]>([])

  async function load() {
    try {
      const data = await listWarehouses({ page: 1, size: 200 })
      opts.value = (data.items ?? []).map((w) => ({ value: w.id, label: `${w.code} ${w.name}` }))
    } catch {
      opts.value = []
    }
  }

  void load()
  return { opts, load }
}

/** 库位下拉（ast_location），按仓库分组展示 */
export function useLocationOptions() {
  const opts = ref<(AssetOption & { warehouseId: number })[]>([])

  async function load() {
    try {
      const data: AssetLocationOption[] = await listAllLocations()
      opts.value = (data ?? []).map((l) => ({
        value: l.id,
        label: l.warehouseName ? `${l.warehouseName} / ${l.code}` : l.code,
        warehouseId: l.warehouseId,
      }))
    } catch {
      opts.value = []
    }
  }

  void load()
  return { opts, load }
}

/** 存货下拉（ast_item） */
export function useItemOptions() {
  const opts = ref<AssetOption[]>([])
  const items = ref<AssetItemOption[]>([])

  async function load() {
    try {
      const data: AssetItemOption[] = await listAllItems()
      items.value = data ?? []
      opts.value = items.value.map((i) => ({
        value: i.id,
        label: `${i.code} ${i.name}${i.spec ? ` (${i.spec})` : ''}`,
      }))
    } catch {
      items.value = []
      opts.value = []
    }
  }

  void load()
  return { opts, items, load }
}

/** 样件下拉（ast_prototype） */
export function usePrototypeOptions() {
  const opts = ref<AssetOption[]>([])

  async function load() {
    try {
      const data: AssetPrototypeOption[] = await listAllPrototypes()
      opts.value = (data ?? []).map((p) => ({ value: p.id, label: `${p.code} ${p.name}` }))
    } catch {
      opts.value = []
    }
  }

  void load()
  return { opts, load }
}

/** 工具下拉（ast_tool） */
export function useToolOptions() {
  const opts = ref<AssetOption[]>([])

  async function load() {
    try {
      const data: AssetToolOption[] = await listAllTools()
      opts.value = (data ?? []).map((x) => ({ value: x.id, label: `${x.toolNo} ${x.name}` }))
    } catch {
      opts.value = []
    }
  }

  void load()
  return { opts, load }
}

/** 固定资产下拉（ast_asset），用于处置单选择待处置资产 */
export function useFixedAssetOptions() {
  const opts = ref<AssetOption[]>([])

  async function load() {
    try {
      const data = await listAssets({ page: 1, size: 200 })
      opts.value = (data.items ?? []).map((a) => ({
        value: a.id,
        label: `${a.assetNo} ${a.name}`,
      }))
    } catch {
      opts.value = []
    }
  }

  void load()
  return { opts, load }
}

/**
 * 供应公司下拉（crm_customer，partner_type = supplier/both）。
 * 远程搜索，避免一次性拉全量往来单位。
 */
export function useSupplierOptions() {
  const opts = ref<AssetOption[]>([])
  const loading = ref(false)

  async function search(q: string) {
    loading.value = true
    try {
      const data = await customerOptions(q, 30, 'supplier')
      opts.value = (data ?? []).map((c) => ({ value: Number(c.id), label: c.label }))
    } catch {
      opts.value = []
    } finally {
      loading.value = false
    }
  }

  void search('')
  return { opts, loading, search }
}
