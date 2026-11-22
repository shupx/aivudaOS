export const CONFIG_TRANSFER_FORMAT_VERSION = 1

export function deepClone(value) {
  if (value === undefined) return undefined
  return JSON.parse(JSON.stringify(value))
}

export function formatConfigTimestamp(date = new Date()) {
  const pad = (value) => String(value).padStart(2, '0')
  return [
    date.getFullYear(),
    pad(date.getMonth() + 1),
    pad(date.getDate()),
    '-',
    pad(date.getHours()),
    pad(date.getMinutes()),
    pad(date.getSeconds()),
  ].join('')
}

export function safeConfigFilenamePart(value, fallback = 'aivudaos') {
  const cleaned = String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return cleaned || fallback
}

export function buildConfigExportFilename(hostname, date = new Date()) {
  return `${safeConfigFilenamePart(hostname)}-${formatConfigTimestamp(date)}-config.json`
}

export function flattenConfigLeaves(value, prefix = '') {
  if (Array.isArray(value)) {
    return [{
      path: prefix,
      value,
    }]
  }

  if (isPlainRecord(value)) {
    const entries = []
    for (const [key, child] of Object.entries(value)) {
      if (!prefix && String(key).startsWith('_')) {
        continue
      }
      const path = prefix ? `${prefix}.${key}` : key
      if (isPlainRecord(child) && Object.keys(child).length > 0) {
        entries.push(...flattenConfigLeaves(child, path))
      } else {
        entries.push({
          path,
          value: deepClone(child),
        })
      }
    }
    return entries
  }

  return prefix
    ? [{
      path: prefix,
      value: deepClone(value),
    }]
    : []
}

export function nestedGet(data, path) {
  const parts = String(path || '').split('.').filter(Boolean)
  let current = data
  for (const part of parts) {
    if (!isPlainRecord(current) && !Array.isArray(current)) return undefined
    if (!Object.prototype.hasOwnProperty.call(current, part)) return undefined
    current = current[part]
  }
  return current
}

export function nestedSet(data, path, value) {
  const parts = String(path || '').split('.').filter(Boolean)
  if (!parts.length) return
  let current = data
  for (let index = 0; index < parts.length - 1; index += 1) {
    const part = parts[index]
    if (!isPlainRecord(current[part])) {
      current[part] = {}
    }
    current = current[part]
  }
  current[parts[parts.length - 1]] = deepClone(value)
}

export function isValueEqual(left, right) {
  return JSON.stringify(left) === JSON.stringify(right)
}

export function valueToTransferText(value) {
  if (value === undefined) return '-'
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value)
  } catch {
    return String(value)
  }
}

export function createConfigExportDocument({
  meta,
  includeSystem,
  selectedApps,
  systemData,
  appItems,
}) {
  const apps = appItems
    .filter((item) => selectedApps.has(String(item?.app_id || '')))
    .map((item) => ({
      app_id: String(item.app_id || ''),
      name: String(item.name || item.app_id || ''),
      version: String(item.app_version || ''),
      autostart: Boolean(item.autostart),
      running: Boolean(item.running),
      parameters: deepClone(item.data || {}),
    }))

  return {
    format_version: CONFIG_TRANSFER_FORMAT_VERSION,
    human_header: {
      description: 'AivudaOS config export. This human_header is ignored during import.',
      aivudaos_version: String(meta?.aivudaos_version || ''),
      avahi_hostname: String(meta?.avahi_hostname || ''),
      exported_at: meta?.exported_at || Math.floor(Date.now() / 1000),
      exported_at_iso: new Date().toISOString(),
      os_parameters: meta?.os_parameters || null,
      selected: {
        system_parameters: Boolean(includeSystem),
        app_count: apps.length,
      },
    },
    payload: {
      system_parameters: includeSystem ? deepClone(systemData || {}) : null,
      apps,
    },
  }
}

export function parseConfigImportDocument(text) {
  let parsed
  try {
    parsed = JSON.parse(String(text || ''))
  } catch (err) {
    throw new Error('Invalid JSON config file')
  }

  if (!isPlainRecord(parsed)) {
    throw new Error('Config file must be a JSON object')
  }
  if (Number(parsed.format_version || 0) !== CONFIG_TRANSFER_FORMAT_VERSION) {
    throw new Error(`Unsupported config format version: ${parsed.format_version || '-'}`)
  }
  if (!isPlainRecord(parsed.payload)) {
    throw new Error('Config file payload is missing')
  }

  const payload = parsed.payload
  const systemParameters = isPlainRecord(payload.system_parameters)
    ? payload.system_parameters
    : null
  const apps = Array.isArray(payload.apps)
    ? payload.apps
      .filter((item) => isPlainRecord(item))
      .map((item) => ({
        app_id: String(item.app_id || ''),
        name: String(item.name || item.app_id || ''),
        version: String(item.version || ''),
        autostart: item.autostart === undefined ? null : Boolean(item.autostart),
        running: item.running === undefined ? null : Boolean(item.running),
        parameters: isPlainRecord(item.parameters) ? item.parameters : {},
      }))
      .filter((item) => item.app_id)
    : []

  return {
    formatVersion: CONFIG_TRANSFER_FORMAT_VERSION,
    humanHeader: parsed.human_header || null,
    systemParameters,
    apps,
  }
}

function isPlainRecord(value) {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
