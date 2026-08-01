'use strict'

const fs = require('fs')

const target = '/wiki/server/core/localization.js'
const requireLine = "const yaml = require('js-yaml')"
const injection = `${requireLine}\nconst fakecoEnglish = require('../locales/fakeco-curated-en.json')`
const marker = '    // -> Load dev locale files if present'
const merge = `    // FakeCo offline fallback: Wiki.js 2 normally downloads translations from the\n    // discontinued graph.requarks.io service. Merge curated English last with\n    // overwrite=false so valid DB translations win while missing keys are filled.\n    if (locale === 'en') {\n      _.forOwn(fakecoEnglish, (data, ns) => {\n        this.namespaces.push(ns)\n        this.engine.addResourceBundle(locale, ns, data, true, false)\n      })\n    }\n\n`

let source = fs.readFileSync(target, 'utf8')
if (source.includes('fakecoEnglish')) process.exit(0)
if (!source.includes(requireLine) || !source.includes(marker)) {
  throw new Error('Unsupported Wiki.js localization.js layout; refusing a partial patch')
}
source = source.replace(requireLine, injection).replace(marker, merge + marker)
fs.writeFileSync(target, source)
