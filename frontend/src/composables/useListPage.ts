import { computed, onMounted, reactive, ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useI18n } from 'vue-i18n'

export interface StatusTab {
  value: string
  labelKey?: string
  label?: string
  count?: number
}

export interface UseListPageOptions<T> {
  fetch: (params: Record<string, unknown>) => Promise<{ items: T[]; total: number }>
  exportFn?: (params: Record<string, unknown>) => Promise<void>
  defaultSize?: number
  defaultStatus?: string
  autoLoad?: boolean
  onLoaded?: (items: T[], total: number) => void
}

export function useListPage<T = unknown>(options: UseListPageOptions<T>) {
  const { t } = useI18n()
  const loading = ref(false)
  const items = ref<T[]>([]) as Ref<T[]>
  const total = ref(0)
  const error = ref<string | null>(null)

  const query = reactive<Record<string, unknown>>({
    page: 1,
    size: options.defaultSize ?? 20,
    q: '',
    status: options.defaultStatus ?? 'all',
    filters: {} as Record<string, unknown>,
    range: {} as Record<string, unknown>,
  })

  const statusTabs = ref<StatusTab[]>([])

  function buildParams(): Record<string, unknown> {
    const params: Record<string, unknown> = {
      page: query.page,
      size: query.size,
    }
    if (query.q) params.q = query.q
    if (query.status) params.status = query.status
    const filters = (query.filters ?? {}) as Record<string, unknown>
    for (const [k, v] of Object.entries(filters)) {
      if (v !== undefined && v !== null && v !== '') {
        params[`filters[${k}]`] = v
      }
    }
    const range = (query.range ?? {}) as Record<string, unknown>
    for (const [k, v] of Object.entries(range)) {
      if (v !== undefined && v !== null && v !== '') {
        params[`range[${k}]`] = v
      }
    }
    for (const [k, v] of Object.entries(query)) {
      if (['page', 'size', 'q', 'status', 'filters', 'range'].includes(k)) continue
      if (v !== undefined && v !== null && v !== '') params[k] = v
    }
    return params
  }

  function exportParams(): Record<string, unknown> {
    const p = buildParams()
    delete p.page
    delete p.size
    return p
  }

  async function load() {
    loading.value = true
    error.value = null
    try {
      const data = await options.fetch(buildParams())
      items.value = data.items ?? []
      total.value = data.total ?? items.value.length
      options.onLoaded?.(items.value, total.value)
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e)
      error.value = msg || t('common.message.loadFailed')
      items.value = []
      total.value = 0
    } finally {
      loading.value = false
    }
  }

  function search() {
    query.page = 1
    void load()
  }

  function reset() {
    query.page = 1
    query.q = ''
    query.status = options.defaultStatus ?? 'all'
    query.filters = {}
    query.range = {}
    void load()
  }

  function refresh() {
    void load()
  }

  function setPage(page: number) {
    query.page = page
    void load()
  }

  function setSize(size: number) {
    query.size = size
    query.page = 1
    void load()
  }

  function setStatus(status: string) {
    query.status = status
    query.page = 1
    void load()
  }

  async function exportList() {
    if (!options.exportFn) return
    try {
      await options.exportFn(exportParams())
      ElMessage.success(t('common.message.exportSuccess'))
    } catch {
      /* http layer already notified */
    }
  }

  const pagination = computed(() => ({
    total: total.value,
    page: query.page as number,
    size: query.size as number,
  }))

  if (options.autoLoad !== false) {
    onMounted(() => {
      void load()
    })
  }

  return {
    loading,
    items,
    total,
    error,
    query,
    statusTabs,
    pagination,
    buildParams,
    exportParams,
    load,
    search,
    reset,
    refresh,
    setPage,
    setSize,
    setStatus,
    exportList,
  }
}
