/** FormDesigner 结构操作纯函数：输入数组视为父级 v-model 所有（只读），
 * 一律返回新数组，绝不原地修改 —— 组件拿到结果后 emit('update:fields', next)。
 * 返回 null 表示无效操作（调用方直接忽略）。
 */
import type { OaField, OaFieldType } from '@/api/types'

/** 生成不冲突的字段 key：text_1 / text_2 ... */
export function nextFieldKey(fields: OaField[], type: OaFieldType): string {
  let i = fields.length + 1
  let key = `${type}_${i}`
  while (fields.some((f) => f.key === key)) key = `${type}_${++i}`
  return key
}

/** 在 at（默认末尾）插入字段 */
export function insertFieldAt(fields: OaField[], field: OaField, at?: number): OaField[] {
  const next = [...fields]
  next.splice(at ?? fields.length, 0, field)
  return next
}

/** 上移/下移一个字段；越界或不存在返回 null */
export function swapField(fields: OaField[], key: string, dir: -1 | 1): OaField[] | null {
  const idx = fields.findIndex((f) => f.key === key)
  const target = idx + dir
  if (idx < 0 || target < 0 || target >= fields.length) return null
  const next = [...fields]
  const a = next[idx]!
  next[idx] = next[target]!
  next[target] = a
  return next
}

/** 按 key 删除字段；不存在返回 null */
export function removeField(fields: OaField[], key: string): OaField[] | null {
  if (!fields.some((f) => f.key === key)) return null
  return fields.filter((f) => f.key !== key)
}

/** 复制字段（深拷贝嵌套配置，key 加 _copy/_copy2... 后缀去重），插入到源字段之后 */
export function duplicateField(
  fields: OaField[],
  key: string,
): { next: OaField[]; copy: OaField } | null {
  const idx = fields.findIndex((f) => f.key === key)
  if (idx < 0) return null
  const src = fields[idx]!
  const copy: OaField = {
    ...src,
    options: src.options ? [...src.options] : undefined,
    mappings: src.mappings ? src.mappings.map((m) => ({ ...m })) : undefined,
    cascade: src.cascade ? { parent: src.cascade.parent, map: { ...src.cascade.map } } : undefined,
    showWhen: src.showWhen ? structuredClone(src.showWhen) : undefined,
    requiredWhen: src.requiredWhen ? structuredClone(src.requiredWhen) : undefined,
    readonlyWhen: src.readonlyWhen ? structuredClone(src.readonlyWhen) : undefined,
  }
  let n = 1
  copy.key = `${src.key}_copy`
  while (fields.some((f) => f.key === copy.key)) copy.key = `${src.key}_copy${++n}`
  const next = [...fields]
  next.splice(idx + 1, 0, copy)
  return { next, copy }
}

/** 画布拖拽排序：把 key 字段移动到落点 index（落点按删除前下标计） */
export function moveFieldTo(
  fields: OaField[],
  key: string,
  index: number,
): { next: OaField[]; item: OaField } | null {
  const from = fields.findIndex((f) => f.key === key)
  if (from < 0) return null
  const next = [...fields]
  const [item] = next.splice(from, 1)
  // 从前面挪走一个元素后，落点下标随之前移
  const to = from < index ? index - 1 : index
  next.splice(to, 0, item!)
  return { next, item: item! }
}
