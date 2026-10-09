// Keep warning presentation shared by version switching and upload/overwrite.
export function formatConfigMigrationWarnings(result, t) {
  const warnings = result?.config_migration_warnings || []
  if (!warnings.length) return ''
  const lines = warnings.map((warning) => {
    const action = t(`apps.migrationAction.${warning.action || 'fallback'}`)
    return `${warning.path}: ${warning.reason} — ${action}`
  })
  return [t('apps.migrationWarning'), ...lines].join('\n')
}
