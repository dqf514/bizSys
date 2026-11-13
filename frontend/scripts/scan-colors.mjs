#!/usr/bin/env node
/**
 * 色值扫描（UI-B）：src 下的 vue/ts/css 不允许出现裸 hex 颜色，一律用 --bs-* 令牌。
 * 例外（刻意保留）：
 *   - ALLOWED_FILES 白名单（如登录页固定深色品牌区、报价单打印白纸）；
 *   - 含 resolveToken( / fallback 的行——chartTheme 令牌解析器的兜底字面值；
 *   - styles/tokens.css（token:build 生成物，源头是 tokens/*.tokens.json）。
 */
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const srcDir = join(dirname(fileURLToPath(import.meta.url)), '..', 'src')

const ALLOWED_FILES = new Set([
  'modules/auth/Login.vue',
  'modules/sales/pages/QuotationPrint.vue',
  'modules/sales/components/QuotationPreview.vue',
  'utils/chartTheme.ts',
])

const HEX = /#[0-9a-fA-F]{3,8}\b/
const ALLOW_LINE = /resolveToken\(|fallback/i

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    if (statSync(p).isDirectory()) {
      if (name !== 'node_modules') yield* walk(p)
    } else if (/\.(vue|ts|css)$/.test(name)) {
      yield p
    }
  }
}

const hits = []
for (const file of walk(srcDir)) {
  const rel = relative(srcDir, file).replace(/\\/g, '/')
  if (rel === 'styles/tokens.css' || ALLOWED_FILES.has(rel)) continue
  const lines = readFileSync(file, 'utf8').split('\n')
  lines.forEach((line, i) => {
    if (HEX.test(line) && !ALLOW_LINE.test(line)) hits.push(`${rel}:${i + 1}  ${line.trim()}`)
  })
}

if (hits.length) {
  console.error(`[scan-colors] found ${hits.length} line(s) with hardcoded hex colors:`)
  for (const h of hits) console.error(`  ${h}`)
  process.exit(1)
}
console.log('[scan-colors] OK — no hardcoded hex colors outside tokens/allowlist')
