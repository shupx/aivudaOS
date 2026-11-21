export const ROS_DOMAIN_SECTION = 'ros2-domain-parameters'
export const GLOBAL_DOMAIN_PATH = 'sys.ros2_default_domain_id'

function isDomainField(key, schema, value) {
  if (['boolean', 'array', 'object'].includes(schema.type) || typeof value === 'boolean') return false
  const words = key.replace(/([a-z0-9])([A-Z])/g, '$1_$2').toLowerCase()
  const description = [schema.title, schema.description].filter(Boolean).join(' ')
  const annotated = schema['x-ros-domain'] === true ||
    /\b(?:ros\s*2?|dds)[\s_-]*(?:domain|域)|\bdomain[\s_-]*id\b|(?:ROS\s*2?|DDS)\s*通信域/i.test(description)
  if (annotated) return true
  if (!/(?:^|[_-])(?:domain|domian)(?:[_-]?id)?$/.test(words)) return false
  // Plain "domain" can also be a DNS name. Only admit numeric settings there.
  if (/id$/.test(words) || /(?:ros2?|dds)[_-]/.test(words)) return true
  return ['integer', 'number'].includes(schema.type) || /^-?\d+$/.test(String(value ?? ''))
}

export function appDomainRows(apps, globalDomain) {
  const rows = []
  for (const app of apps) {
    function visit(data, defaults, schema, rawSchema, segments, label) {
      const value = data ?? defaults ?? schema.default ?? rawSchema.default
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
      if (!segments.length || !isDomainField(String(label ?? segments.at(-1)), meta, value)) return
      const inherited = value === -1 || value === '-1' || value == null
      const number = typeof value === 'string' && /^\d+$/.test(value) ? Number(value) : value
      const valid = Number.isInteger(number) && number >= 0 && number <= 232
      rows.push({
        appId: app.app_id, name: app.name || app.app_id, path: segments.join('.'), segments,
        value, schemaObj: meta, type: meta.type || (typeof value === 'string' ? 'string' : 'integer'),
        domain: inherited ? globalDomain : valid ? number : null,
        source: inherited ? 'inherited' : !valid ? 'invalid' : data == null ? 'packageDefault' : 'override',
      })
    }
    visit(app.data, app.default_data, app.normalized_schema || app.schema || {}, app.schema || {}, [])
  }
  return rows.sort((a, b) => a.name.localeCompare(b.name) || a.path.localeCompare(b.path))
}
