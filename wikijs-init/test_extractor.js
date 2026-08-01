'use strict'

const assert = require('assert')
const fs = require('fs')
const os = require('os')
const path = require('path')
const { buildBundle, extractKeys, humanize } = require('./build-offline-locale')

const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'fakeco-wikijs-locale-'))
try {
  fs.writeFileSync(path.join(temp, 'app.js'), `
    vm.$t('welcome.createhome')
    vm.$tc("comments.replyCount", count)
    WIKI.lang.t('admin.security.apiKey')
    vm.$t('common:actions.apply')
    vm.$t('common:singleKey')
  `)
  const { files, keys } = extractKeys([temp])
  assert.strictEqual(files.length, 1)
  assert.deepStrictEqual(keys, [
    'actions.apply', 'admin.security.apiKey', 'comments.replyCount', 'singleKey',
    'welcome.createhome'
  ])
  assert.strictEqual(humanize('comments.replyCount'), 'Reply Count')
  assert.strictEqual(humanize('admin.security.apiKey'), 'API Key')

  const bundle = buildBundle(keys, {
    'welcome.createhome': 'Create Home Page',
    'welcome.goadmin': 'Go to Administration'
  })
  assert.strictEqual(bundle.common.welcome.createhome, 'Create Home Page')
  assert.strictEqual(bundle.common.welcome.goadmin, 'Go to Administration')
  assert.strictEqual(bundle.common.comments.replyCount, 'Reply Count')
  assert.deepStrictEqual(
    buildBundle([...keys].reverse(), { 'welcome.createhome': 'Create Home Page' }),
    buildBundle(keys, { 'welcome.createhome': 'Create Home Page' })
  )
  assert.throws(() => extractKeys([path.join(temp, 'missing')]), /Unsupported Wiki\.js layout/)
} finally {
  fs.rmSync(temp, { recursive: true, force: true })
}
console.log('extractor tests passed')
