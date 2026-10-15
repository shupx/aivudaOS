const STORAGE_PREFIX = 'AIVUDAOS_PARAMETER_HISTORY_V1:'
const MAX_VALUES = 20
const MAX_VALUE_LENGTH = 2048

export function parameterHistoryKey(row) {
  if (!row || row.readonly || row.schemaObj?.writeOnly || row.schemaObj?.format === 'password') return ''
  if (/(password|passwd|secret|token|api[_-]?key|credential)/i.test(String(row.path || ''))) return ''
  return JSON.stringify([row.scope || 'app', row.appId || '', row.path || '', row.type || row.value_type || 'string'])
}

export function readParameterValueHistory(key) {
  if (!key) return []
  try {
    const values = JSON.parse(localStorage.getItem(STORAGE_PREFIX + key) || '[]')
    if (!Array.isArray(values)) return []
    return [...new Set(values.filter(value => typeof value === 'string' && value.trim() && value.length <= MAX_VALUE_LENGTH))].slice(0, MAX_VALUES)
  } catch {
    return []
  }
}

export function rememberParameterValue(key, value) {
  const text = String(value ?? '')
  if (!key || !text.trim() || text.length > MAX_VALUE_LENGTH) return readParameterValueHistory(key)
  const values = [text, ...readParameterValueHistory(key).filter(item => item !== text)].slice(0, MAX_VALUES)
  try {
    localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(values))
  } catch {
    // A full or unavailable browser store must not prevent configuration saves.
  }
  return values
}
