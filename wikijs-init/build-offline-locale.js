'use strict'

const fs = require('fs')
const path = require('path')

const SOURCE_EXTENSIONS = new Set(['.js', '.pug', '.vue'])
const KEY = '(?:[a-z][A-Za-z0-9_-]*:)?[a-z][A-Za-z0-9_-]*(?:\\.[A-Za-z0-9_-]+)*'
const PATTERNS = [
  new RegExp('\\.\\$(?:t|tc)\\(\\s*([\\\'"`])(' + KEY + ')\\1', 'g'),
  new RegExp('\\b(?:WIKI\\.lang|i18n|i18next)\\.(?:t|tc)\\(\\s*([\\\'"`])(' + KEY + ')\\1', 'g'),
  new RegExp('\\b(?:translate|localize)\\(\\s*([\\\'"`])(' + KEY + ')\\1', 'g')
]

function walk(root) {
  if (!fs.existsSync(root) || !fs.statSync(root).isDirectory()) {
    throw new Error(`Unsupported Wiki.js layout: source root missing: ${root}`)
  }
  const files = []
  for (const entry of fs.readdirSync(root, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
    const item = path.join(root, entry.name)
    if (entry.isDirectory()) files.push(...walk(item))
    else if (SOURCE_EXTENSIONS.has(path.extname(entry.name))) files.push(item)
  }
  return files
}

function extractKeys(roots) {
  const keys = new Set()
  const files = [...new Set(roots.flatMap(walk))].sort()
  for (const file of files) {
    const source = fs.readFileSync(file, 'utf8')
    for (const pattern of PATTERNS) {
      pattern.lastIndex = 0
      let match
      while ((match = pattern.exec(source)) !== null) {
        const raw = match[2]
        keys.add(raw.startsWith('common:') ? raw.slice('common:'.length) : raw)
      }
    }
  }
  return { files, keys: [...keys].sort() }
}

const WORD_OVERRIDES = new Map([
  ['api', 'API'], ['id', 'ID'], ['ip', 'IP'], ['sso', 'SSO'], ['ssl', 'SSL'],
  ['tls', 'TLS'], ['url', 'URL'], ['uri', 'URI'], ['2fa', '2FA'], ['oauth', 'OAuth'],
  ['github', 'GitHub'], ['gitlab', 'GitLab'], ['ldap', 'LDAP'], ['smtp', 'SMTP']
])

function humanize(key) {
  const leaf = key.split('.').at(-1)
  const spaced = leaf
    .replace(/[_-]+/g, ' ')
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/([A-Z]+)([A-Z][a-z])/g, '$1 $2')
    .trim()
  return spaced.split(/\s+/).filter(Boolean).map(word => {
    const known = WORD_OVERRIDES.get(word.toLowerCase())
    return known || word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
  }).join(' ')
}

function setNested(target, dotted, value) {
  const parts = dotted.split('.')
  let cursor = target
  for (const part of parts.slice(0, -1)) cursor = cursor[part] ||= {}
  cursor[parts.at(-1)] = value
}

function buildBundle(keys, overrides = {}) {
  const bundle = {}
  for (const token of [...keys].sort()) {
    const colon = token.indexOf(':')
    const namespace = colon === -1 ? 'common' : token.slice(0, colon)
    const key = colon === -1 ? token : token.slice(colon + 1)
    const value = overrides[token] || overrides[key] || humanize(key)
    setNested(bundle[namespace] ||= {}, key, value)
  }
  // Curated keys remain available even if upstream references move between bundles.
  for (const token of Object.keys(overrides).sort()) {
    const colon = token.indexOf(':')
    const namespace = colon === -1 ? 'common' : token.slice(0, colon)
    const key = colon === -1 ? token : token.slice(colon + 1)
    setNested(bundle[namespace] ||= {}, key, overrides[token])
  }
  return bundle
}

function parseArgs(argv) {
  const result = {}
  for (let i = 0; i < argv.length; i += 2) result[argv[i].replace(/^--/, '')] = argv[i + 1]
  return result
}

function main(argv) {
  const args = parseArgs(argv)
  const roots = (args.roots || '').split(',').filter(Boolean)
  if (!roots.length || !args.overrides || !args.output) throw new Error('Required: --roots, --overrides, --output')
  const minimum = Number(args['min-keys'] || 1)
  const expected = args['expected-keys'] === undefined ? null : Number(args['expected-keys'])
  const { files, keys } = extractKeys(roots)
  if (keys.length < minimum) {
    throw new Error(`Unsupported Wiki.js layout: extracted ${keys.length} keys; expected at least ${minimum}`)
  }
  if (expected !== null && keys.length !== expected) {
    throw new Error(`Unsupported Wiki.js layout: extracted ${keys.length} keys; pinned layout requires ${expected}`)
  }
  const overrides = JSON.parse(fs.readFileSync(args.overrides, 'utf8'))
  const bundle = buildBundle(keys, overrides)
  const finalKeys = new Set(keys)
  for (const key of Object.keys(overrides)) finalKeys.add(key)
  fs.writeFileSync(args.output, JSON.stringify(bundle, null, 2) + '\n')
  console.log(`FakeCo offline locale: ${keys.length} extracted keys, ${finalKeys.size} final keys, ${Object.keys(overrides).length} curated overrides, ${files.length} files scanned`)
}

module.exports = { buildBundle, extractKeys, humanize, setNested }
if (require.main === module) main(process.argv.slice(2))
