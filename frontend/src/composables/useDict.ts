import { ref } from 'vue'
import { dictItems } from '@/api/admin'
import type { DictItemOption } from '@/api/types'
import { useI18n } from 'vue-i18n'

const cache = new Map<string, DictItemOption[]>()

export function useDict() {
  const { locale } = useI18n()

  async function load(type: string, force = false): Promise<DictItemOption[]> {
    if (!force && cache.has(type)) return cache.get(type)!
    try {
      const list = await dictItems(type)
      cache.set(type, list ?? [])
      return list ?? []
    } catch {
      return []
    }
  }

  function labelOf(item: DictItemOption): string {
    return locale.value === 'en-US' && item.labelEn ? item.labelEn : item.label
  }

  function optionsOf(list: DictItemOption[]) {
    return list.map((x) => ({ label: labelOf(x), value: x.value }))
  }

  async function options(type: string, force = false) {
    return optionsOf(await load(type, force))
  }

  function clearCache() {
    cache.clear()
  }

  return { load, options, labelOf, optionsOf, clearCache }
}

/** simple reactive dict options for a type */
export function useDictOptions(type: string) {
  const items = ref<DictItemOption[]>([])
  const loading = ref(false)
  const { options: toOptions } = useDict()
  const opts = ref<{ label: string; value: string }[]>([])

  async function reload() {
    loading.value = true
    try {
      opts.value = await toOptions(type)
    } finally {
      loading.value = false
    }
  }

  void reload()
  return { items, opts, loading, reload }
}
