#!/usr/bin/env node
/** Compare zh-CN / en-US locale key sets. Exit 1 on any mismatch. */
import { readdirSync, readFileSync } from 'node:fs'
import { join, dirname, basename } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const localesDir = join(here, '..', 'src', 'locales')

function flatten(obj, prefix = '') {
  const keys = []
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k
    if (v && typeof v === 'object' && !Array.isArray(v)) {
      keys.push(...flatten(v, key))
    } else {
      keys.push(key)
    }
  }
  return keys
}

const zhDir = join(localesDir, 'zh-CN')
const enDir = join(localesDir, 'en-US')
const zhFiles = readdirSync(zhDir).filter((f) => f.endsWith('.json')).sort()
const enFiles = readdirSync(enDir).filter((f) => f.endsWith('.json')).sort()

let failed = 0
const zhOnlyFiles = zhFiles.filter((f) => !enFiles.includes(f))
const enOnlyFiles = enFiles.filter((f) => !zhFiles.includes(f))
if (zhOnlyFiles.length || enOnlyFiles.length) {
  console.error('[i18n-check] file set mismatch:')
  if (zhOnlyFiles.length) console.error('  only in zh-CN:', zhOnlyFiles.join(', '))
  if (enOnlyFiles.length) console.error('  only in en-US:', enOnlyFiles.join(', '))
  failed = 1
}

for (const file of zhFiles) {
  if (!enFiles.includes(file)) continue
  const domain = basename(file, '.json')
  const zh = JSON.parse(readFileSync(join(zhDir, file), 'utf8'))
  const en = JSON.parse(readFileSync(join(enDir, file), 'utf8'))
  const zhKeys = new Set(flatten(zh))
  const enKeys = new Set(flatten(en))
  const missingEn = [...zhKeys].filter((k) => !enKeys.has(k))
  const missingZh = [...enKeys].filter((k) => !zhKeys.has(k))
  if (missingEn.length) {
    failed = 1
    console.error(`[i18n-check] ${domain}: missing in en-US:`)
    for (const k of missingEn) console.error(`   ${domain}.${k}`)
  }
  if (missingZh.length) {
    failed = 1
    console.error(`[i18n-check] ${domain}: missing in zh-CN:`)
    for (const k of missingZh) console.error(`   ${domain}.${k}`)
  }
}

// 源码里 t('ns.key') 用到的键必须在 zh-CN 存在（防"两种语言同时缺键"与命名空间错挂漏网）
const srcDir = join(here, '..', 'src')
const NAMESPACES = new Set(zhFiles.map((f) => basename(f, '.json')))
const available = new Set()
for (const file of zhFiles) {
  const domain = basename(file, '.json')
  const zh = JSON.parse(readFileSync(join(zhDir, file), 'utf8'))
  for (const k of flatten(zh)) available.add(`${domain}.${k}`)
}
const used = new Set()
function* walkSrc(dir) {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name)
    if (entry.isDirectory()) yield* walkSrc(p)
    else if (/\.(vue|ts)$/.test(entry.name)) yield p
  }
}
const tCall = /(?:\$?t|te)\(\s*['"]([A-Za-z_][\w.]*)['"]/g
for (const file of walkSrc(srcDir)) {
  const text = readFileSync(file, 'utf8')
  for (const m of text.matchAll(tCall)) {
    const key = m[1]
    if (NAMESPACES.has(key.split('.')[0])) used.add(key)
  }
}
const missingUsed = [...used].filter((k) => !available.has(k)).sort()
if (missingUsed.length) {
  failed = 1
  console.error('[i18n-check] used but not defined in zh-CN:')
  for (const k of missingUsed) console.error(`   ${k}`)
}

if (failed) {
  console.error('[i18n-check] FAILED')
  process.exit(1)
}
console.log(`[i18n-check] OK — ${zhFiles.length} domains, key sets identical, ${used.size} used keys all defined`)
