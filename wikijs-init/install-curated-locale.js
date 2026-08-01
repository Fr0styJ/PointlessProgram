'use strict'

const fs = require('fs')

const target = '/wiki/server/core/localization.js'
const clientTarget = '/wiki/assets/js/app.js'
const masterViewTarget = '/wiki/server/views/master.pug'
const requireLine = "const yaml = require('js-yaml')"
const injection = `${requireLine}\nconst fakecoEnglish = require('../locales/fakeco-offline-en.json')`
const marker = '    // -> Load dev locale files if present'
const merge = `    // FakeCo offline fallback: Wiki.js 2 normally downloads translations from the\n    // discontinued graph.requarks.io service. Merge curated English last with\n    // overwrite=false so valid DB translations win while missing keys are filled.\n    if (locale === 'en') {\n      _.forOwn(fakecoEnglish, (data, ns) => {\n        this.namespaces.push(ns)\n        this.engine.addResourceBundle(locale, ns, data, true, false)\n      })\n    }\n\n`

let source = fs.readFileSync(target, 'utf8')
if (!source.includes('fakecoEnglish')) {
  if (!source.includes(requireLine) || !source.includes(marker)) {
    throw new Error('Unsupported Wiki.js localization.js layout; refusing a partial patch')
  }
  source = source.replace(requireLine, injection).replace(marker, merge + marker)
  fs.writeFileSync(target, source)
}

// Wiki.js caches namespace payloads in browser localStorage for 24 hours. Use
// a FakeCo-owned cache namespace so browsers which previously cached raw keys
// immediately fetch the repaired bundle after this image is deployed.
const cacheNeedle = 'backendOptions:[{expirationTime:864e5},{loadPath:'
const cacheReplacement = 'backendOptions:[{expirationTime:864e5,prefix:"fakeco_i18next_v1_"},{loadPath:'
let client = fs.readFileSync(clientTarget, 'utf8')
if (!client.includes('fakeco_i18next_v1_')) {
  const occurrences = client.split(cacheNeedle).length - 1
  if (occurrences !== 1) {
    throw new Error(`Unsupported Wiki.js client localization layout (${occurrences} cache markers)`)
  }
  client = client.replace(cacheNeedle, cacheReplacement)
  fs.writeFileSync(clientTarget, client)
}

// The pinned upstream template hard-codes its original app.js cache token.
// Change it alongside the localStorage namespace so existing browsers fetch
// the patched client bundle instead of reusing the upstream asset indefinitely.
const assetNeedle = "src='/_assets/js/app.js?1777631845'"
const assetReplacement = "src='/_assets/js/app.js?fakeco-locale-v1'"
let masterView = fs.readFileSync(masterViewTarget, 'utf8')
if (!masterView.includes(assetReplacement)) {
  const occurrences = masterView.split(assetNeedle).length - 1
  if (occurrences !== 1) {
    throw new Error(`Unsupported Wiki.js master template (${occurrences} app.js markers)`)
  }
  masterView = masterView.replace(assetNeedle, assetReplacement)
  fs.writeFileSync(masterViewTarget, masterView)
}
