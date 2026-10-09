#!/usr/bin/env node
/**
 * Scan .vue/.ts for hardcoded Chinese literals (excluding locales/ and comments).
 * Warn-only by default; pass --strict to exit 1.
 */
import { readdirSync, readFileSync, statSync } from 'node:fs'
import { join, dirname, extname, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const srcDir = join(here, '..', 'src')
const strict = process.argv.includes('--strict')

const SKIP_DIRS = new Set(['locales', 'node_modules', 'dist', 'styles'])
const EXTS = new Set(['.ts', '.vue'])
const CJK = /[一-鿿]/

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name)
    const st = statSync(p)
    if (st.isDirectory()) {
      if (!SKIP_DIRS.has(name)) walk(p, out)
    } else if (EXTS.has(extname(name))) {
      out.push(p)
    }
  }
  return out
}

function stripComments(code) {
  return code
    .replace(/\/\*[\s\S]*?\*\//g, '')
    .replace(/^\s*\/\/.*$/gm, '')
    .replace(/<!--[\s\S]*?-->/g, '')
}

const findings = []
for (const file of walk(srcDir)) {
  const raw = readFileSync(file, 'utf8')
  const code = stripComments(raw)
  const lines = code.split('\n')
  lines.forEach((line, i) => {
    if (!CJK.test(line)) return
    // allow i18n key-ish comments already stripped; allow import paths
    if (/from\s+['"]/.test(line) && !CJK.test(line.replace(/from\s+['"][^'"]+['"]/g, ''))) return
    findings.push({ file: relative(srcDir, file), line: i + 1, text: line.trim().slice(0, 120) })
  })
}

if (findings.length === 0) {
  console.log('[scan-literal] OK — no hardcoded Chinese literals')
  process.exit(0)
}

console.log(`[scan-literal] found ${findings.length} line(s) with Chinese literals:`)
for (const f of findings) {
  console.log(`  src/${f.file}:${f.line}  ${f.text}`)
}
if (strict) process.exit(1)
process.exit(0)
