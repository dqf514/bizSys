/**
 * Vue Boolean prop 默认值守卫。
 *
 * Vue 对 `type: Boolean` 的 props 有个反直觉的规则：**未传值时默认取 `false`**，
 * 而不是 `undefined`。所以下面这种写法是错的：
 *
 * ```ts
 * const props = defineProps<{ showPagination?: boolean }>()
 * // v-if="props.showPagination !== false"  →  未传值时 props.showPagination === false
 * //                                          → 条件恒为 false → 组件永远"关闭"
 * ```
 *
 * 踩过的坑：列表页的分页条（翻页 + 总条数）从来没渲染过，
 * 因为 `ResponsiveTable.showPagination` 未传值即 false。
 *
 * 本守卫规则：**凡是出现「未传即允许」写法（`x !== false`）的可选 Boolean prop，
 * 都必须在 `withDefaults` 里显式给出默认值。**
 */
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { describe, expect, it } from 'vitest'

// vitest 以 frontend/ 为根目录运行
const SRC_DIR = join(process.cwd(), 'src')

function vueFiles(dir: string): string[] {
  const out: string[] = []
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name.startsWith('.')) continue
      out.push(...vueFiles(full))
    } else if (entry.name.endsWith('.vue')) {
      out.push(full)
    }
  }
  return out
}

/** 取出 defineProps<{ ... }>() 类型块里所有「可选 Boolean」属性名 */
function optionalBooleanProps(src: string): string[] {
  const names: string[] = []
  const blocks = src.matchAll(/defineProps<\{([\s\S]*?)\}>/g)
  for (const block of blocks) {
    const body = block[1] ?? ''
    for (const m of body.matchAll(/(\w+)\?\s*:\s*boolean\b/g)) {
      const name = m[1]
      if (name) names.push(name)
    }
  }
  return names
}

/** withDefaults(...) 的默认值区域里是否显式给了该属性的默认值 */
function hasExplicitDefault(src: string, name: string): boolean {
  const idx = src.indexOf('withDefaults(')
  if (idx < 0) return false
  const region = src.slice(idx, idx + 2000)
  return new RegExp(`\\b${name}\\s*:`).test(region)
}

/** 是否出现「未传即允许」的写法 */
function usesDefaultOnSemantics(src: string, name: string): boolean {
  return new RegExp(`\\b${name}\\s*!==\\s*false`).test(src)
}

describe('boolean prop default value guard', () => {
  const files = vueFiles(SRC_DIR)

  it('scans component files', () => {
    expect(files.length).toBeGreaterThan(50)
  })

  it('optional boolean props with default-on semantics must declare an explicit default', () => {
    const violations: string[] = []
    for (const file of files) {
      const src = readFileSync(file, 'utf-8')
      for (const name of new Set(optionalBooleanProps(src))) {
        if (!usesDefaultOnSemantics(src, name)) continue
        if (!hasExplicitDefault(src, name)) {
          violations.push(`${file.replace(SRC_DIR, 'src/')} :: ${name}`)
        }
      }
    }
    expect(violations, 'boolean prop without an explicit default is false when omitted').toEqual([])
  })

  it('list pagination bar renders by default (pager + total count)', () => {
    const src = readFileSync(join(SRC_DIR, 'components/common/ResponsiveTable.vue'), 'utf-8')
    expect(src).toMatch(/showPagination\s*:\s*true/)
    expect(src).toContain('v-if="props.showPagination"')
    expect(src).toContain('class="table-pagination"')
    expect(src).toContain('common.table.total')
  })

  it('ListTable forwards showPagination explicitly', () => {
    const src = readFileSync(join(SRC_DIR, 'components/list/ListTable.vue'), 'utf-8')
    expect(src).toMatch(/showPagination\s*:\s*true/)
    expect(src).toContain(':show-pagination="props.showPagination"')
  })
})
