import assert from 'node:assert/strict'
import test from 'node:test'
import { formatConfigMigrationWarnings } from '../aivudaos/resources/ui/src/services/core/configMigration.js'
import en from '../aivudaos/resources/ui/src/i18n/locales/en-US.js'
import zh from '../aivudaos/resources/ui/src/i18n/locales/zh-CN.js'

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
