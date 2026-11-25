import assert from 'node:assert/strict'
import test from 'node:test'
import { formatConfigMigrationWarnings } from '../aivudaos/resources/ui/src/services/core/configMigration.js'
import { getConfigValue, setConfigValue, nestedGet, nestedSet } from '../aivudaos/resources/ui/src/services/core/configTransfer.js'
import en from '../aivudaos/resources/ui/src/i18n/locales/en-US.js'
import zh from '../aivudaos/resources/ui/src/i18n/locales/zh-CN.js'

test('editor paths preserve array indices and literal keys; imported leaves are copied', () => {
  const draft = { lanes: [{ keep: true }], '': { mode: 'literal' }, mode: 'normal' }
  const path = ['lanes', 1, 'ros.domain']
  const value = { id: 7 }
  setConfigValue(draft, path, value)
  assert.equal(getConfigValue(draft, path), value)
  assert.deepEqual(draft.lanes[0], { keep: true })
  assert.equal(getConfigValue(draft, '.mode'), 'literal')
  assert.equal(nestedGet(draft, '.mode'), 'normal')

  const imported = {}
  nestedSet(imported, path, value)
  value.id = 8
  assert.equal(nestedGet(imported, path).id, 7)
  assert.ok(Array.isArray(imported.lanes))
  nestedSet(imported, 'lanes.0', 'object leaf')
  assert.deepEqual(imported.lanes, { 0: 'object leaf' })
})

for (const [locale, messages] of Object.entries({ en, zh })) {
  const t = (key) => key.split('.').reduce((value, part) => value?.[part], messages)
  test(`${locale}: successful migration does not show an alert`, () => {
    assert.equal(formatConfigMigrationWarnings({}, t), '')
    assert.equal(formatConfigMigrationWarnings({ config_migration_warnings: [] }, t), '')
  })
  test(`${locale}: completion results identify every field and fallback action`, () => {
    const warnings = ['used_target', 'used_default', 'skipped', 'requires_configuration'].map((action, index) => ({
      path: `$.field${index}`, reason: `reason${index}`, action,
    }))
    const text = formatConfigMigrationWarnings({ config_migration_warnings: warnings }, t)
    assert.ok(text.startsWith(messages.apps.migrationWarning))
    for (const warning of warnings) {
      assert.ok(text.includes(warning.path))
      assert.ok(text.includes(warning.reason))
      assert.ok(text.includes(messages.apps.migrationAction[warning.action]))
    }
    assert.ok(!text.includes('undefined'))
  })
}
