export const ROS_DOMAIN_SECTION = 'ros2-domain-parameters'
export const GLOBAL_DOMAIN_PATH = 'sys.ros2_default_domain_id'

const snakeCase = key => key.replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase()

function isDomainField(key, parents, schema, value) {
  const types = [].concat(schema.type || [])
  if (types.some(t => ['boolean', 'array', 'object'].includes(t)) ||
      typeof value === 'boolean' || (value !== null && typeof value === 'object')) return false
  const words = snakeCase(key)
  const description = [schema.title, schema.description].filter(Boolean).join(' ')
  const annotated = schema['x-ros-domain'] === true ||
    /\b(?:ros\s*2?|dds)[\s_-]*(?:domain|域)|(?:ROS\s*2?|DDS)\s*通信域/i.test(description)
  if (annotated) return true
  if (!/(?:^|[_-])(?:domain|domian)(?:[_-]?id)?$/.test(words) && !/\bdomain[\s_-]*id\b/i.test(description)) return false
  // Unqualified IDs can be UUIDs or DNS names rather than ROS domains.
  if (/(?:^|[._-])(?:ros2?|dds)(?:$|[._-])/.test(snakeCase([...parents, key].join('.'))) ||
      /\b(?:ros\s*2?|dds)\b/i.test(description)) return true
  return types.some(t => ['integer', 'number'].includes(t)) || typeof value === 'number' ||
    (typeof value === 'string' && /^-?\d+$/.test(value))
}

export function isDomainReadonly(row, bindings) {
  return Boolean(row.readonly || row.schemaObj?.readOnly ||
    bindings?.some(path => row.path === path || row.path.startsWith(path + '.')))
}

export function parseDomainInput(row, text) {
  const schema = row.schemaObj || {}
  const min = Math.max(row.scope === 'sys' ? 0 : -1, schema.minimum ?? -1)
  const max = Math.min(232, schema.maximum ?? 232)
  const types = [].concat(schema.type || [])
  const choices = Array.isArray(schema.enum) ? schema.enum : null
  if (text === null || (!choices && text === '')) {
    const nullable = types.includes('null') || (!types.length && choices?.includes(null))
    return { valid: row.scope !== 'sys' && Boolean(nullable) && (!choices || choices.includes(null)), min, max, value: null }
  }
  const number = Number(text)
  // A select supplies a typed enum value; a text input supplies a string.
  const value = choices?.includes(text) ? text : row.type === 'string' ? String(text) : number
  const typeAllowed = !types.length || (typeof value === 'string' ? types.includes('string') : types.some(t => ['integer', 'number'].includes(t)))
  const valid = typeAllowed && /^-?\d+$/.test(String(text)) && Number.isSafeInteger(number) &&
    number >= min && number <= max && (!choices || choices.includes(value))
  return { valid, min, max, value }
}

export function appDomainRows(apps, globalDomain) {
  const rows = []
  for (const app of apps) {
    function visit(data, defaults, schema, rawSchema, segments, label) {
      // A saved null explicitly inherits the launch domain, even if the package has a default.
      const value = [data, defaults, schema.default, rawSchema.default].find(candidate => candidate !== undefined)
      if (Array.isArray(value)) {
        value.forEach((item, i) => visit(data?.[i], defaults?.[i] ?? item, schema.items || {}, rawSchema.items || {}, [...segments, i]))
        return
      }
      const properties = schema.properties || {}
      const keys = new Set([...Object.keys(properties), ...Object.keys(rawSchema.properties || {})])
      for (const object of [defaults, data]) {
        if (object && typeof object === 'object') Object.keys(object).forEach(key => keys.add(key))
      }
      if (keys.size) {
        for (const key of keys) {
          if (['__proto__', 'prototype', 'constructor'].includes(key)) continue
          let label = key
          if (key === 'value') label = data?.name ?? data?.key ?? defaults?.name ?? defaults?.key ?? key
          if (key === 'id' && /^(?:domain|domian)$/i.test(segments.at(-1))) label = 'domain_id'
          visit(data?.[key], defaults?.[key], properties[key] || {}, rawSchema.properties?.[key] || {}, [...segments, key], label)
        }
        return
      }
      const meta = { ...rawSchema, ...schema }
      if (!segments.length || !isDomainField(String(label ?? segments.at(-1)), segments.slice(0, -1), meta, value)) return
      const types = [].concat(meta.type || [])
      const fallbackType = typeof value === 'string' ? 'string' : 'integer'
      const type = types.includes(fallbackType) ? fallbackType : types.find(t => t !== 'null') || fallbackType
      const inherited = value === -1 || value === '-1' || value == null
      const number = typeof value === 'string' && /^\d+$/.test(value) ? Number(value) : value
      const valid = Number.isInteger(number) && number >= 0 && number <= 232
      rows.push({
        appId: app.app_id, name: app.name || app.app_id, path: segments.join('.'), segments,
        value, schemaObj: meta, type,
        domain: inherited ? globalDomain : valid ? number : null,
        source: inherited ? 'inherited' : !valid ? 'invalid' : app.version === 0 || data == null ? 'packageDefault' : 'override',
      })
    }
    visit(app.data, app.default_data, app.normalized_schema || app.schema || {}, app.schema || {}, [])
  }
  return rows.sort((a, b) => a.name.localeCompare(b.name) || a.path.localeCompare(b.path))
}
